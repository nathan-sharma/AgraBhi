// rover_arduino.ino
// Runs on the Arduino. It does two jobs over one serial line (9600 baud) to the Pi:
//   1. Actuator:    the Pi sends 'E' to extend, 'R' to retract or 'Z' to stop where it is.
//                   The Arduino answers "Actuator extended." / "Actuator retracted." /
//                   "Actuator stopped." so the Pi knows the command arrived.
//   2. Soil sensor: every 300 ms it prints   DATA,<moisture>,<temperature>
//                   (the same line format datacollecter.py was reading).
#include <Servo.h>

const int actuatorPin = 9;
Servo actuator;
unsigned long lastUpdateTime = 0;
const unsigned long updateInterval = 300;


// ---------------------------------------------------------------------------
// ACTUATOR TYPE: this decides how 'Z' (stop) works.
//   true  = position type (a "linear servo" wired straight to the Arduino). The pulse width
//           is the position to go to: 1000 = fully retracted, 2000 = fully extended. It has
//           no "stop" pulse, so the Arduino keeps a running estimate of where the actuator
//           is, and Z tells it to go to that spot. Set fullStrokeMs to the time your
//           actuator takes to travel its whole stroke, or the stop will be off the mark.
//   false = speed type (a motor driver or speed controller sits between the Arduino and the
//           actuator). 1000 / 2000 run the motor one way or the other and 1500 switches it
//           off, so Z sends 1500.
// ---------------------------------------------------------------------------
const bool POSITION_TYPE = true;
const unsigned long fullStrokeMs = 35000;

float estimatedUs = 1000;            // where the actuator probably is right now, as a pulse width
int targetUs = 1000;                 // where it was last told to go
unsigned long lastEstimateTime = 0;

void updateEstimate() {      // move the estimate towards the target at the actuator's speed
  unsigned long now = millis();
  float step = (now - lastEstimateTime) * 1000.0 / fullStrokeMs; // Added missing '*'
  lastEstimateTime = now;
  
  if (estimatedUs < targetUs) {
    estimatedUs = min(estimatedUs + step, (float)targetUs);
  } else if (estimatedUs > targetUs) {
    estimatedUs = max(estimatedUs - step, (float)targetUs);
  }
}

void moveActuator(int pulseUs) {
  targetUs = pulseUs;
  actuator.writeMicroseconds(pulseUs);
}


// ---------------------------------------------------------------------------
// SOIL SENSOR: PUT YOUR SENSOR CODE HERE
// Copy the reading code from your existing soil sensor sketch into
// readSoilSensor(): set moisture and temperature, then return true.
// Anything the sensor needs once at power-up goes in setupSoilSensor().
// While readSoilSensor() returns false, no DATA lines are sent, and the Pi
// logs samples with the moisture and temperature columns blank.
// ---------------------------------------------------------------------------
void setupSoilSensor() {
}

bool readSoilSensor(float &moisture, float &temperature) {
  return false;
}
// ---------------------------------------------------------------------------


void setup() {
  Serial.begin(9600);
  moveActuator(1000);                // start retracted (set before attach so it is the first pulse sent)
  actuator.attach(actuatorPin);
  setupSoilSensor();
  delay(100);
}


void loop() {
  updateEstimate();

  if (Serial.available() > 0) {
    char command = Serial.read();

    if (command == 'E') { // extend
      moveActuator(2000);
      Serial.println("Actuator extended.");
    } else if (command == 'R') { // retract
      moveActuator(1000);
      Serial.println("Actuator retracted.");
    } else if (command == 'Z') { // stop where it is
      moveActuator(POSITION_TYPE ? (int)estimatedUs : 1500);
      Serial.println("Actuator stopped.");
    }
  }

  unsigned long currentTime = millis();
  if (currentTime - lastUpdateTime >= updateInterval) {
    lastUpdateTime = currentTime;
    float moisture, temperature;
    if (readSoilSensor(moisture, temperature)) {
      Serial.print("DATA,");
      Serial.print(moisture);
      Serial.print(",");
      Serial.println(temperature);
    }
  }
}
