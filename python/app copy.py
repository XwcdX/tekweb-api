from mysql.connector import pooling
import heapq
from flask import Flask, request, jsonify
import threading
import time

app = Flask(__name__)

class User:
    def __init__(self, user_id):
        self.user_id = user_id
        self.following = {}

    def follow(self, other_user, weight=1):
        self.following[other_user] = weight

    # interaction
    def interact(self, other_user, weight=1):
        if other_user in self.interactions:
            self.interactions[other_user] += weight
        else:
            self.interactions[other_user] = weight

    def get_interactions(self):
        return self.interactions

class Recommendation:
    def __init__(self):
        self.nodes = {}

    def add_user(self, user_id):
        if user_id not in self.nodes:
            self.nodes[user_id] = User(user_id)

    def add_follow(self, user_id, follow_id, weight=1):
        self.add_user(user_id)
        self.add_user(follow_id)
        self.nodes[user_id].follow(self.nodes[follow_id], weight)

    def recommend_users(self, user_id, top_n=5):
        if user_id not in self.nodes:
            return []
        user_node = self.nodes[user_id]
        directly_followed = user_node.following
        candidate_scores = {}
        for followed_user, direct_weight in directly_followed.items():
            for second_degree_user, second_weight in followed_user.following.items():
                if second_degree_user != user_node and second_degree_user not in directly_followed:
                    score = direct_weight + second_weight
                    candidate_scores[second_degree_user] = candidate_scores.get(second_degree_user, 0) + score
        sorted_candidates = sorted(candidate_scores.items(), key=lambda x: (-x[1], x[0].user_id))
        return [(candidate.user_id, score) for candidate, score in sorted_candidates[:top_n]]
    # interaction
    def add_interaction(self, user_id, interacted_user_id, weight=1):
        self.add_user(user_id)
        self.add_user(interacted_user_id)
        self.nodes[user_id].interact(self.nodes[interacted_user_id], weight)

    def most_interacted_with(self, user_id, top_n=5):
        if user_id not in self.nodes:
            return []
        user_node = self.nodes[user_id]
        # Mendapatkan interaksi pengguna dan mengurutkannya berdasarkan bobot interaksi
        interactions = user_node.get_interactions()
        sorted_interactions = sorted(interactions.items(), key=lambda x: -x[1])  # Urutkan berdasarkan bobot tertinggi
        return [(interacted_user.user_id, score) for interacted_user, score in sorted_interactions[:top_n]]

class UserContribution:
    def __init__(self, user_id, contributions):
        self.user_id = user_id
        self.contributions = contributions

    def __lt__(self, other):
        return self.contributions > other.contributions

class Leaderboard:
    def __init__(self):
        self.subject_leaderboards = {}
        self.entry_map = {}

    def update_leaderboard(self, subject_id, user_id, contributions):
        if subject_id not in self.subject_leaderboards:
            self.subject_leaderboards[subject_id] = []
            self.entry_map[subject_id] = {}

        leaderboard = self.subject_leaderboards[subject_id]
        entry_map = self.entry_map[subject_id]

        if user_id in entry_map:
            entry = entry_map[user_id]
            entry.contributions += contributions
            heapq.heapify(leaderboard)
        else:
            new_entry = UserContribution(user_id, contributions)
            heapq.heappush(leaderboard, new_entry)
            entry_map[user_id] = new_entry

    def get_top_contributors(self, subject_id, top_n):
        if subject_id not in self.subject_leaderboards:
            return []

        leaderboard = self.subject_leaderboards[subject_id]
        return [
            {"user_id": entry.user_id, "contributions": entry.contributions}
            for entry in heapq.nsmallest(top_n, leaderboard)
        ]

graph = Recommendation()
leaderboard = Leaderboard()

last_processed_time = None
last_processed_time_graph = None
db_lock = threading.Lock()

conn_pool = pooling.MySQLConnectionPool(
    pool_name="mypool",
    pool_size=10,
    host='127.0.0.1',
    user='root',
    password='',
    database='tekweb_project'
)

def fetch_from_db(query, params=None):
    conn = conn_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute(query, params or ())
            return cursor.fetchall()
    finally:
        conn.close()

def build_graph_from_db():
    global last_processed_time_graph
    query = "SELECT * FROM follows"
    params = ()
    if last_processed_time_graph:
        query += " WHERE created_at > %s"
        params = (last_processed_time_graph,)
    query += " ORDER BY created_at ASC"

    rows = fetch_from_db(query, params)

    for row in rows:
        graph.add_follow(row['follower_id'], row['followed_id'])
        last_processed_time_graph = row['created_at']

def monitor_db():
    while True:
        try:
            build_graph_from_db()
            time.sleep(2)
        except Exception as e:
            print(f"Error monitoring database: {e}")

@app.route('/recommend', methods=['GET'])
def recommend_api():
    try:
        user_id = request.args.get('user')
        
        if not user_id:
            return jsonify({
                "code": 400,
                "success": False,
                "message": "User ID is required.",
                "data": None
            }), 400

        if user_id not in graph.nodes:
            return jsonify({
                "code": 404,
                "success": False,
                "message": "User not found.",
                "data": None
            }), 404

        recommendations = graph.recommend_users(user_id)
        return jsonify({
            "code": 200,
            "success": True,
            "message": "Recommendations retrieved successfully.",
            "data": recommendations
        })

    except Exception as e:
        return jsonify({
            "code": 500,
            "success": False,
            "message": "An error occurred while processing the request.",
            "error": str(e)
        }), 500
        
def build_leaderboard_from_db():
    global last_processed_time
    query = """
        SELECT 
            contributions.user_id, 
            contributions.subject_id, 
            COUNT(*) AS total_contributions
        FROM (
            SELECT 
                q.user_id, 
                q.subject_id, 
                q.updated_at
            FROM questions q
            UNION ALL
            SELECT 
                a.user_id, 
                q.subject_id, 
                a.updated_at
            FROM answers a
            JOIN questions q 
            ON a.question_id = q.id
        ) AS contributions
    """
    
    if last_processed_time:
        query += " WHERE contributions.updated_at > %s"

    query += """
        GROUP BY contributions.user_id, contributions.subject_id
        ORDER BY total_contributions DESC
    """
    
    params = (last_processed_time,) if last_processed_time else ()
    rows = fetch_from_db(query, params)
    
    with db_lock:
        for row in rows:
            subject_id = row['subject_id']
            user_id = row['user_id']
            total_contributions = row['total_contributions']
            leaderboard.update_leaderboard(subject_id, user_id, total_contributions)
            last_processed_time = row['updated_at']

def monitor_leaderboard_db():
    while True:
        try:
            build_leaderboard_from_db()
            time.sleep(2)
        except Exception as e:
            print(f"Error monitoring leaderboard database: {e}")


@app.route('/leaderboard', methods=['GET'])
def leaderboard_api():
    try:
        subject_id = request.args.get('subject')
        top_n = int(request.args.get('top_n', 5))
        if not subject_id:
            return jsonify({
                "code": 400,
                "success": False,
                "message": "Subject ID is required.",
                "data": None
            }), 400

        top_contributors = leaderboard.get_top_contributors(subject_id, top_n)
        return jsonify({
            "code": 200,
            "success": True,
            "message": "Leaderboard retrieved successfully.",
            "data": top_contributors
        })
    
    except Exception as e:
        return jsonify({
            "code": 500,
            "success": False,
            "message": "An error occurred while processing the request.",
            "error": str(e)
        }), 500
# api interactions
@app.route('/most_interacted_with', methods=['GET'])
def most_interacted_with_api():
    try:
        user_id = request.args.get('user')
        top_n = int(request.args.get('top_n', 1))
        
        if not user_id:
            return jsonify({
                "code": 400,
                "success": False,
                "message": "User ID is required.",
                "data": None
            }), 400

        if user_id not in graph.nodes:
            return jsonify({
                "code": 404,
                "success": False,
                "message": "User not found.",
                "data": None
            }), 404

        most_interacted = graph.most_interacted_with(user_id, top_n)
        return jsonify({
            "code": 200,
            "success": True,
            "message": "Most interacted users retrieved successfully.",
            "data": most_interacted
        })
    except Exception as e:
        return jsonify({
            "code": 500,
            "success": False,
            "message": "An error occurred while processing the request.",
            "error": str(e)
        }), 500
    



if __name__ == '__main__':
    threading.Thread(target=monitor_db, daemon=True).start()
    threading.Thread(target=monitor_leaderboard_db, daemon=True).start()
    app.run(debug=True, host='0.0.0.0')