<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Model;

class Subject extends Model
{

    use HasUuids;

    protected $fillable = [
        'name'
    ];

    public static function validationRules()
    {
        return [
            'name'=>'required|string'
        ];
    }

    public static function validationMessages()
    {
        return [
            'name.required' => 'The subject field is required.',
            'name.string' => 'The subject must be a valid string.',
        ];
    }
    
    public function relations(){
        return [
            'questionType',
            'groupQuestion'
        ];
    }

    public function questionType()
    {
        return $this->hasMany(QuestionType::class, 'subject_id');
    }

    public function groupQuestion(){
        return $this->hasMany(GroupQuestion::class, 'subject_id');
    }
}
