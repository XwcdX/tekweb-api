<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Model;

class GroupQuestion extends Model
{
    //
    use HasUuids;

    public function relations(){
        return [];
    }
    
}
