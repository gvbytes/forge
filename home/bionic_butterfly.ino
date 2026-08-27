// Bionic Butterfly Control Sketch
// This sketch demonstrates how to use an Arduino to read a PWM signal from an RC receiver,
// control a servo motor that acts as a wing actuator, and interface with a basic
// flight‑controller loop that keeps the device level using a simple PID controller.
// The code is intentionally lightweight so it can run on an ATmega328P (Arduino Uno).

#include <Servo.h>

// ----- Configuration -----
const uint8_t RECEIVER_PIN = 2;   // PWM input from RC receiver (channel 1)
const uint8_t SERVO_PIN    = 9;   // PWM output to servo motor
const uint8_t GYRO_SCL_PIN = A5; // I2C SCL for MPU6050 (optional)
const uint8_t GYRO_SDA_PIN = A4; // I2C SDA for MPU6050 (optional)

// Servo limits (degrees)
const int SERVO_MIN_ANGLE = 0;
const int SERVO_MAX_ANGLE = 180;

// Receiver pulse width limits (microseconds)
const int RC_MIN_PULSE = 1000;
const int RC_MAX_PULSE = 2000;

// PID parameters for simple level control
const float Kp = 0.5;
const float Ki = 0.0;
const float Kd = 0.1;

// ----- Global Variables -----
Servo wingServo;
volatile uint16_t pulseWidth = 1500; // default neutral
unsigned long lastPulseStart = 0;

// For PID
float integral = 0.0;
float lastError = 0.0;

// MPU6050 (optional)
#include <Wire.h>
#include <Adafruit_MPU6050.h>
Adafruit_MPU6050 mpu;

// ----- Interrupt Service Routine -----
void IRAM_ATTR onPulse() {
  if (digitalRead(RECEIVER_PIN) == HIGH) {
    // Rising edge
    lastPulseStart = micros();
  } else {
    // Falling edge
    pulseWidth = micros() - lastPulseStart;
  }
}

// ----- Setup -----
void setup() {
  Serial.begin(115200);
  pinMode(RECEIVER_PIN, INPUT);
  attachInterrupt(digitalPinToInterrupt(RECEIVER_PIN), onPulse, CHANGE);

  wingServo.attach(SERVO_PIN, 500, 2500); // 0-180 degrees

  // Initialize MPU6050
  Wire.begin(GYRO_SDA_PIN, GYRO_SCL_PIN);
  if (!mpu.begin()) {
    Serial.println("Could not find a valid MPU6050 sensor, check wiring!");
  } else {
    Serial.println("MPU6050 initialized");
    mpu.setAccelerometerRange(MPU6050_RANGE_2_G);
    mpu.setGyroRange(MPU6050_RANGE_250_DEG);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
  }

  Serial.println("Bionic Butterfly ready");
}

// ----- Helper Functions -----
int mapPulseToAngle(uint16_t pulse) {
  // Clamp pulse width
  pulse = constrain(pulse, RC_MIN_PULSE, RC_MAX_PULSE);
  // Map to servo angle
  return map(pulse, RC_MIN_PULSE, RC_MAX_PULSE, SERVO_MIN_ANGLE, SERVO_MAX_ANGLE);
}

float getPitchAngle() {
  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);
  // Simple pitch calculation from accelerometer
  float pitch = atan2(a.acceleration.y, a.acceleration.z) * 180.0 / PI;
  return pitch;
}

// ----- Main Loop -----
void loop() {
  // 1. Read receiver and set wing servo
  int targetAngle = mapPulseToAngle(pulseWidth);
  wingServo.write(targetAngle);

  // 2. Simple level control using pitch angle
  float pitch = getPitchAngle();
  float error = -pitch; // we want pitch = 0
  integral += error * 0.02; // assuming loop ~50Hz
  float derivative = (error - lastError) / 0.02;
  float output = Kp * error + Ki * integral + Kd * derivative;
  lastError = error;

  // Convert PID output to servo adjustment
  int adjustment = constrain(int(output), -10, 10);
  int newAngle = constrain(targetAngle + adjustment, SERVO_MIN_ANGLE, SERVO_MAX_ANGLE);
  wingServo.write(newAngle);

  // 3. Debug output
  Serial.print("Pulse: "); Serial.print(pulseWidth);
  Serial.print(" | Target Angle: "); Serial.print(targetAngle);
  Serial.print(" | Pitch: "); Serial.print(pitch);
  Serial.print(" | Adjusted Angle: "); Serial.println(newAngle);

  delay(20); // 50Hz loop
}