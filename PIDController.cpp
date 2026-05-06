#include "PIDController.h"

PIDController::PIDController(
    float p,
    float i,
    float d
)
{
    kp = p;
    ki = i;
    kd = d;

    previousError = 0.f;
    integral = 0.f;
}

float PIDController::calculate(
    float error,
    float deltaTime
)
{
    if (deltaTime <= 0.f)
        return 0.f;

    integral += error * deltaTime;

    float derivative =
        (error - previousError)
        / deltaTime;

    previousError = error;

    return
        kp * error
        + ki * integral
        + kd * derivative;
}