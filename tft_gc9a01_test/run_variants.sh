#!/bin/bash
cd /d/Github/PertaminaGLD/tft_gc9a01_test
LOG=variants.log; : > $LOG
run() { # name, extra flags, freq
  name="$1"; extra="$2"; freq="$3"
  sed "s/-DSPI_FREQUENCY=4000000/-DSPI_FREQUENCY=$freq/" platformio.base.ini > platformio.ini
  [ -n "$extra" ] && printf "  %s\n" $extra >> platformio.ini
  r=$(pio run -t upload 2>&1 | grep -E "SUCCESS|FAILED" | head -1)
  echo "$(date +%H:%M:%S) $name -> $r" | tee -a $LOG
  sleep 10
}
run "V1 SPI 4MHz (dasar)"            ""                                   4000000
run "V2 invert ON"                   "-DTFT_INVERSION_ON=1"               4000000
run "V3 urutan warna BGR"            "-DTFT_RGB_ORDER=TFT_BGR"            4000000
run "V4 SPI 1MHz"                    ""                                   1000000
run "V5 SPI mode 3"                  "-DTFT_SPI_MODE=SPI_MODE3"           4000000
run "V6 SPI 10MHz"                   ""                                   10000000
cp platformio.base.ini platformio.ini
echo "$(date +%H:%M:%S) SELESAI, platformio.ini dikembalikan ke dasar" | tee -a $LOG
