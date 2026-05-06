#pragma once
#pragma once

class PIDController
{
private:

    float kp;
    float ki;
    float kd;

    float previousError;
    float integral;

public:

    PIDController(
        float p,
        float i,
        float d
    );

    float calculate(
        float error,
        float deltaTime
    );
};