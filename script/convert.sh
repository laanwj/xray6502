#!/bin/bash
# Convert series of images to animated gif
INFILES=''
for i in `seq -f "%03g" 0 39`; do
    echo $i
    convert screenshot_${i}.png -crop 275x350+0+250\! screenshot_${i}_c.png
    INFILES="$INFILES screenshot_${i}_c.png"
done

convert -layers optimize -delay 100 -loop 0 $INFILES flowtracking.gif

