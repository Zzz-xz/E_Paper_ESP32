#include <Arduino.h>
#include "application.h"

/** @brief 联网后等待网站任务，启动时保留面板已有画面。 */
void setup()
{
    Serial.begin(115200);
    application::begin();
}

void loop()
{
    application::tick(millis());
    delay(10);
}
