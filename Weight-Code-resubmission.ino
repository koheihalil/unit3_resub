#include "HX711.h"
#include <Servo.h>

#define DOUT 3
#define CLK 2
#define SERVO_PIN 4

HX711 scale;
Servo wingServo;

float calibrationFactor = 16.42;
int currentAngle = 120;
int targetAngle = 120;
String inputLine = "";
unsigned long lastWeightRead = 0;
unsigned long lastServoMove = 0;

void setup() {
  Serial.begin(9600);
  scale.begin(DOUT, CLK);
  scale.set_scale(calibrationFactor);

  wingServo.attach(SERVO_PIN);
  wingServo.write(currentAngle);

  delay(2000);
  scale.tare();
  Serial.println("READY");
}

void loop() {
  if (millis() - lastWeightRead >= 200) {
    lastWeightRead = millis();

    float currentWeight = scale.get_units(5);
    if (currentWeight < 0) {
      currentWeight = 0;
    }

    Serial.print("W:");
    Serial.println(currentWeight, 1);
  }

  while (Serial.available()) {
    char c = Serial.read();

    if (c == '\n') {
      if (inputLine.startsWith("F:")) {
        int level = inputLine.substring(2).toInt();
        level = constrain(level, 0, 100);
        targetAngle = map(level, 0, 100, 120, 40);
      }

      inputLine = "";
    } else if (c != '\r') {
      inputLine += c;
    }
  }

  if (millis() - lastServoMove >= 20) {
    lastServoMove = millis();

    if (currentAngle < targetAngle) {
      currentAngle++;
    } else if (currentAngle > targetAngle) {
      currentAngle--;
    }

    wingServo.write(currentAngle);
  }
}
