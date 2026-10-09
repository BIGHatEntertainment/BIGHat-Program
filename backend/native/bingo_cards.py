"""alpha.109: Bingo card generator.

Builds printable Music Bingo cards from ONE theme's song list (the same csv/xlsx the Bingo player uses).
  * 24 different song titles per card, a free space (BIG Hat logo) in the centre, B-I-N-G-O header.
  * 4 cards per US Letter page (2 x 2), laid out like the "80's Bingo.pdf" sample.
  * No SharePoint, no preset cards, and NO extra Python package: the PDF is written here with the standard
    library only, so the packaged (PyInstaller) backend needs no new dependency.
"""
from __future__ import annotations

import base64
import math
import random
import re
import zlib
from typing import Any, Dict, List, Optional, Sequence

PAGE_W, PAGE_H = 612, 792
CARD_W = 282
CARD_X = (12, 318)             # left edge of the two columns
CARD_TOP = (23, 449)           # top edge of the two rows (measured from the top of the page)
HEADER_H = 53
CELL_H = 53
CELL_W = CARD_W / 5.0
CARDS_PER_PAGE = 4
MIN_SONGS = 24                 # a card needs 24 different songs (25 squares minus the free space)
LOTERIA_GRID = 4               # alpha.110: Loteria cards are 4 x 4 pictures, no free space
LOTERIA_PICS = LOTERIA_GRID * LOTERIA_GRID
IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
LOTERIA_PX = (420, 600)        # each picture is stored at most this many pixels (w, h): sharp at 300 dpi when printed ~1.3 x 1.8 inches
LOTERIA_PER_PAGE = 2           # alpha.111: Loteria cards print LANDSCAPE, 2 per page, with a dashed cut line down the middle
LOTERIA_PAGE_W, LOTERIA_PAGE_H = 792, 612
MAX_CARDS = 200
FREE_SPACE = (2, 2)

HEADER_FILL = (0.784, 0.784, 1.0)     # lavender, as in the sample
FREE_FILL = (1.0, 1.0, 0.0)           # yellow, as in the sample

# Helvetica advance widths (1/1000 em) for the characters 32..255 (WinAnsi), used to wrap text without a font library.
_W = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584, 761, 556, 761, 222, 556, 333, 1000, 556, 556, 333, 1000, 667, 333, 1000, 761, 611, 761, 761, 222, 222, 333, 333, 350, 556, 1000, 333, 1000, 500, 333, 944, 761, 500, 667, 278, 333, 556, 556, 556, 556, 260, 556, 333, 737, 370, 556, 584, 333, 737, 333, 400, 584, 333, 333, 333, 556, 537, 278, 333, 333, 365, 556, 834, 834, 834, 611, 667, 667, 667, 667, 667, 667, 1000, 722, 667, 667, 667, 667, 278, 278, 278, 278, 722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667, 667, 611, 556, 556, 556, 556, 556, 556, 889, 500, 556, 556, 556, 556, 278, 278, 278, 278, 556, 556, 556, 556, 556, 556, 556, 584, 611, 556, 556, 556, 556, 500, 556, 500]

# The hat logo from the sample card (70 x 70, RGB + alpha), zlib-compressed.
_LOGO_RGB = "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"
_LOGO_ALPHA = "eNrVmNuOwjAMRP3/Pz2wEm3txJeZti8bCVFBcnB8N2b9gr203gDhu34w3JPh7zwuDCD+vB3HcVJwPfKU49BKAa8IXGc2CAU6\
NvpXvBCBQbb858ZcawMcBo4QBRM2h88ncQ4Dpf5j9KVakb39alcbfdQ5AToJiCtPGNot8+3VN0jeO4oQbqUBajG9602SW+4H\
KJSZSL7GTBkPvTRVyGdhWVJK+0gUYyHJlXqnQ5Voasju+CgoiGFpu1omRNi3xfZKARiM5RCwkKUo5LKwFEurlUJJylzUPsBi\
3Lk1AfKQxGdUWYbeBhpFKrEMAgpkzXoixooylkWzdo3oZ0Q0d81b0j1KNmmUrZo11/YTSK5ipStPy5YRjY5N+Zys1nPVZULl\
ZYzv90FbtOkaFIvWBVVSbFViRQzd15H2WdphTr3ViBMmD1Kx6DvrW4o9A8uXrEEjQ87ZN7kJyaiRryzGJmUuhPl1GWX41BXm\
1yTviW0+4jPcgx7yuwzQsxgQhJH/qFi6tTspNdHRE8iph2ey/L/1AVJImbs="
_LOGO_PX = 70

# "BINGO" in Lemonada Bold (the BIG Hat font, backend/assets/fonts/Lemonada-Bold.ttf), drawn as vector outlines so the PDF
# needs no font file and no extra package. Each entry: (advance width, path) in 1/1000 em, y up, cubic curves.
_LEMONADA_BINGO = {
    'B': (789, '727 188 m 727.0 145.3 712.5 108.0 683.5 76.0 c 654.5 44.0 613.3 19.3 560.0 2.0 c 506.7 -15.3 444.3 -24.0 373.0 -24.0 c 264.3 -24.0 185.8 -11.2 137.5 14.5 c 89.2 40.2 65.0 82.0 65.0 140.0 c 65.0 168.7 69.0 211.0 77.0 267.0 c 85.0 323.0 100.3 416.0 123.0 546.0 c 70 653 l 145.3 701.7 214.0 726.0 276.0 726.0 c 317.3 726.0 342.0 706.0 350.0 666.0 c 418.7 705.3 486.0 725.0 552.0 725.0 c 605.3 725.0 647.3 711.5 678.0 684.5 c 708.7 657.5 724.0 620.7 724.0 574.0 c 724.0 527.3 709.8 486.7 681.5 452.0 c 653.2 417.3 611.7 389.3 557.0 368.0 c 610.3 358.0 652.0 337.2 682.0 305.5 c 712.0 273.8 727.0 234.7 727.0 188.0 c h 306 379 m 367.3 383.0 416.0 397.5 452.0 422.5 c 488.0 447.5 506.0 479.3 506.0 518.0 c 506.0 568.0 477.7 593.0 421.0 593.0 c 391.0 593.0 364.0 588.3 340.0 579.0 c 331.3 537.7 320.0 471.0 306.0 379.0 c h 509 201 m 509.0 233.0 498.3 257.8 477.0 275.5 c 455.7 293.2 425.7 302.0 387.0 302.0 c 355.7 302.0 324.3 296.7 293.0 286.0 c 285.0 220.7 278.3 162.3 273.0 111.0 c 288.3 104.3 305.8 99.0 325.5 95.0 c 345.2 91.0 364.3 89.0 383.0 89.0 c 421.0 89.0 451.5 99.2 474.5 119.5 c 497.5 139.8 509.0 167.0 509.0 201.0 c h'),
    'I': (382, '123 546 m 70 653 l 145.3 701.7 214.0 726.0 276.0 726.0 c 327.3 726.0 353.0 694.7 353.0 632.0 c 353.0 608.7 340.7 532.0 316.0 402.0 c 289.3 259.3 276.0 173.7 276.0 145.0 c 276.0 114.3 278.2 89.7 282.5 71.0 c 286.8 52.3 294.7 35.3 306.0 20.0 c 268.0 -10.0 226.7 -25.0 182.0 -25.0 c 139.3 -25.0 108.3 -14.3 89.0 7.0 c 69.7 28.3 60.0 62.7 60.0 110.0 c 60.0 139.3 64.2 183.3 72.5 242.0 c 80.8 300.7 97.7 402.0 123.0 546.0 c h'),
    'N': (863, '797 402 m 770.3 259.3 757.0 173.7 757.0 145.0 c 757.0 114.3 759.2 89.7 763.5 71.0 c 767.8 52.3 775.7 35.3 787.0 20.0 c 767.0 4.0 746.8 -7.5 726.5 -14.5 c 706.2 -21.5 684.0 -25.0 660.0 -25.0 c 600.0 -25.0 552.7 -9.7 518.0 21.0 c 483.3 51.7 453.8 106.5 429.5 185.5 c 405.2 264.5 379.7 384.7 353.0 546.0 c 342 546 l 333.3 492.0 324.7 443.3 316.0 400.0 c 303.3 331.3 293.5 276.0 286.5 234.0 c 279.5 192.0 276.0 162.0 276.0 144.0 c 276.0 113.3 278.2 88.7 282.5 70.0 c 286.8 51.3 294.7 34.3 306.0 19.0 c 268.0 -11.0 226.7 -26.0 182.0 -26.0 c 139.3 -26.0 108.3 -15.3 89.0 6.0 c 69.7 27.3 60.0 61.7 60.0 109.0 c 60.0 138.3 64.2 182.3 72.5 241.0 c 80.8 299.7 97.7 401.3 123.0 546.0 c 70 653 l 145.3 701.7 214.0 726.0 276.0 726.0 c 331.3 726.0 374.0 714.0 404.0 690.0 c 434.0 666.0 459.0 621.0 479.0 555.0 c 499.0 489.0 520.7 385.0 544.0 243.0 c 554 243 l 560.7 290.3 577.3 391.7 604.0 547.0 c 561 654 l 631.7 702.7 697.0 727.0 757.0 727.0 c 808.3 727.0 834.0 695.7 834.0 633.0 c 834.0 618.3 830.2 588.5 822.5 543.5 c 814.8 498.5 806.3 451.3 797.0 402.0 c h'),
    'G': (780, '668 -141 m 630.7 -170.3 591.0 -185.0 549.0 -185.0 c 507.7 -185.0 477.5 -175.7 458.5 -157.0 c 439.5 -138.3 430.0 -110.7 430.0 -74.0 c 430.0 -60.0 432.0 -41.0 436.0 -17.0 c 411.3 -25.7 386.3 -30.0 361.0 -30.0 c 257.0 -30.0 175.7 -2.8 117.0 51.5 c 58.3 105.8 29.0 181.3 29.0 278.0 c 29.0 363.3 49.5 440.2 90.5 508.5 c 131.5 576.8 188.0 630.2 260.0 668.5 c 332.0 706.8 412.7 726.0 502.0 726.0 c 566.0 726.0 617.0 714.5 655.0 691.5 c 693.0 668.5 712.0 637.7 712.0 599.0 c 712.0 567.7 700.8 541.8 678.5 521.5 c 656.2 501.2 627.7 491.0 593.0 491.0 c 559.7 491.0 528.8 500.0 500.5 518.0 c 472.2 536.0 450.0 561.3 434.0 594.0 c 398.7 581.3 366.8 559.0 338.5 527.0 c 310.2 495.0 287.8 457.0 271.5 413.0 c 255.2 369.0 247.0 322.7 247.0 274.0 c 247.0 213.3 258.0 166.0 280.0 132.0 c 302.0 98.0 332.7 81.0 372.0 81.0 c 412.0 81.0 445.8 95.7 473.5 125.0 c 501.2 154.3 516.3 190.7 519.0 234.0 c 441 309 l 473.0 329.0 506.3 345.3 541.0 358.0 c 575.7 370.7 608.3 377.0 639.0 377.0 c 667.0 377.0 686.7 371.7 698.0 361.0 c 709.3 350.3 715.0 333.3 715.0 310.0 c 715.0 295.3 706.3 258.7 689.0 200.0 c 671.7 136.7 658.7 85.2 650.0 45.5 c 641.3 5.8 637.0 -29.3 637.0 -60.0 c 637.0 -98.0 647.3 -125.0 668.0 -141.0 c h'),
    'O': (773, '753 424 m 753.0 339.3 735.3 262.8 700.0 194.5 c 664.7 126.2 616.0 72.5 554.0 33.5 c 492.0 -5.5 422.7 -25.0 346.0 -25.0 c 282.7 -25.0 227.2 -12.0 179.5 14.0 c 131.8 40.0 95.0 76.3 69.0 123.0 c 43.0 169.7 30.0 223.0 30.0 283.0 c 30.0 369.0 47.8 445.7 83.5 513.0 c 119.2 580.3 166.5 632.5 225.5 669.5 c 284.5 706.5 348.0 725.0 416.0 725.0 c 460.7 725.0 492.7 717.3 512.0 702.0 c 531.3 686.7 541.0 662.3 541.0 629.0 c 541.0 621.7 540.3 612.0 539.0 600.0 c 559.7 614.7 583.7 622.0 611.0 622.0 c 655.7 622.0 690.5 604.5 715.5 569.5 c 740.5 534.5 753.0 486.0 753.0 424.0 c h 612 296 m 525.3 336.0 482.0 399.7 482.0 487.0 c 482.0 518.3 491.0 546.3 509.0 571.0 c 490.3 573.7 477.0 575.0 469.0 575.0 c 425.0 575.0 386.3 561.8 353.0 535.5 c 319.7 509.2 293.8 473.7 275.5 429.0 c 257.2 384.3 248.0 335.7 248.0 283.0 c 248.0 217.7 261.0 167.7 287.0 133.0 c 313.0 98.3 348.7 81.0 394.0 81.0 c 426.7 81.0 458.5 90.2 489.5 108.5 c 520.5 126.8 547.0 152.3 569.0 185.0 c 591.0 217.7 605.3 254.7 612.0 296.0 c h'),
}
_LEMONADA_EXTRA = {
    'L': (553, '543 111 m 543.0 67.7 530.0 34.2 504.0 10.5 c 478.0 -13.2 441.0 -25.0 393.0 -25.0 c 349.7 -25.0 308.0 -19.0 268.0 -7.0 c 242.0 -19.7 213.3 -26.0 182.0 -26.0 c 139.3 -26.0 108.3 -15.3 89.0 6.0 c 69.7 27.3 60.0 61.7 60.0 109.0 c 60.0 139.0 64.3 183.7 73.0 243.0 c 81.7 302.3 98.3 403.3 123.0 546.0 c 70 653 l 145.3 701.7 214.0 726.0 276.0 726.0 c 327.3 726.0 353.0 694.7 353.0 632.0 c 353.0 617.3 349.2 587.5 341.5 542.5 c 333.8 497.5 325.3 450.3 316.0 401.0 c 289.3 258.3 276.0 172.7 276.0 144.0 c 276 136 l 384 136 l 435.3 143.3 484.7 156.3 532.0 175.0 c 539.3 156.3 543.0 135.0 543.0 111.0 c h'),
    'T': (644, '664 618 m 664.0 576.7 650.7 544.2 624.0 520.5 c 597.3 496.8 561.0 485.0 515.0 485.0 c 494.3 485.0 471.3 486.7 446.0 490.0 c 428.0 400.0 414.3 328.7 405.0 276.0 c 395.7 223.3 391.0 186.0 391.0 164.0 c 391.0 99.3 401.0 51.0 421.0 19.0 c 381.0 -11.0 339.7 -26.0 297.0 -26.0 c 253.0 -26.0 221.7 -13.5 203.0 11.5 c 184.3 36.5 175.0 75.7 175.0 129.0 c 175.0 160.3 179.7 206.3 189.0 267.0 c 198.3 327.7 213.3 413.7 234.0 525.0 c 210 526 l 58 487 l 46.0 515.7 40.0 547.3 40.0 582.0 c 40.0 623.3 53.3 655.8 80.0 679.5 c 106.7 703.2 143.0 715.0 189.0 715.0 c 212.3 715.0 235.7 713.3 259.0 710.0 c 282.3 706.7 310.7 701.7 344.0 695.0 c 376.0 688.3 403.3 683.3 426.0 680.0 c 448.7 676.7 471.3 674.7 494.0 674.0 c 646 713 l 658.0 684.3 664.0 652.7 664.0 618.0 c h'),
    'E': (629, '586 175 m 593.3 157.7 597.0 136.3 597.0 111.0 c 597.0 67.7 584.0 34.2 558.0 10.5 c 532.0 -13.2 495.0 -25.0 447.0 -25.0 c 390.3 -25.0 337.0 -15.3 287.0 4.0 c 257.7 -16.0 222.7 -26.0 182.0 -26.0 c 139.3 -26.0 108.3 -15.3 89.0 6.0 c 69.7 27.3 60.0 61.7 60.0 109.0 c 60.0 139.0 64.3 184.2 73.0 244.5 c 81.7 304.8 98.3 405.3 123.0 546.0 c 70 653 l 145.3 701.7 214.0 726.0 276.0 726.0 c 315.3 726.0 339.7 707.3 349.0 670.0 c 394.3 672.7 437.7 678.0 479.0 686.0 c 520.3 694.0 571.0 705.7 631.0 721.0 c 636.3 696.3 639.0 674.7 639.0 656.0 c 639.0 605.3 622.0 565.5 588.0 536.5 c 554.0 507.5 507.3 493.0 448.0 493.0 c 417.3 493.0 380.0 498.7 336.0 510.0 c 329.3 472.0 321.0 426.0 311.0 372.0 c 331.0 368.0 351.0 366.0 371.0 366.0 c 461 389 l 464.3 375.7 466.0 359.7 466.0 341.0 c 466.0 312.3 456.3 289.8 437.0 273.5 c 417.7 257.2 391.0 249.0 357.0 249.0 c 337.0 249.0 314.7 252.0 290.0 258.0 c 280.7 198.7 276.0 160.7 276.0 144.0 c 276 136 l 438 136 l 489.3 143.3 538.7 156.3 586.0 175.0 c h'),
    'R': (747, '747 30 m 732.3 15.3 710.7 2.5 682.0 -8.5 c 653.3 -19.5 627.3 -25.0 604.0 -25.0 c 557.3 -25.0 520.5 -12.8 493.5 11.5 c 466.5 35.8 442.3 78.3 421.0 139.0 c 387 235 l 383 235 l 346.3 235.0 314.3 239.7 287.0 249.0 c 279.7 203.7 276.0 168.7 276.0 144.0 c 276.0 113.3 278.2 88.7 282.5 70.0 c 286.8 51.3 294.7 34.3 306.0 19.0 c 268.0 -11.0 226.7 -26.0 182.0 -26.0 c 139.3 -26.0 108.3 -15.3 89.0 6.0 c 69.7 27.3 60.0 61.7 60.0 109.0 c 60.0 138.3 64.2 182.3 72.5 241.0 c 80.8 299.7 97.7 401.3 123.0 546.0 c 70 653 l 145.3 701.7 214.0 726.0 276.0 726.0 c 307.3 726.0 329.0 714.3 341.0 691.0 c 385.0 713.0 436.0 724.0 494.0 724.0 c 540.0 724.0 579.8 714.2 613.5 694.5 c 647.2 674.8 672.8 649.0 690.5 617.0 c 708.2 585.0 717.0 551.0 717.0 515.0 c 717.0 470.3 706.5 428.0 685.5 388.0 c 664.5 348.0 633.3 315.0 592.0 289.0 c 616.7 223.7 642.3 168.7 669.0 124.0 c 695.7 79.3 721.7 48.0 747.0 30.0 c h 330 360 m 377.3 360.0 416.5 373.0 447.5 399.0 c 478.5 425.0 494.0 459.0 494.0 501.0 c 494.0 525.7 485.2 547.7 467.5 567.0 c 449.8 586.3 425.0 596.0 393.0 596.0 c 379.7 596.0 365.0 593.3 349.0 588.0 c 345.7 565.3 334.7 505.7 316.0 409.0 c 307 362 l 317.7 360.7 325.3 360.0 330.0 360.0 c h'),
    'A': (767, '663 377 m 663.0 287.0 667.2 213.3 675.5 156.0 c 683.8 98.7 701.0 52.0 727.0 16.0 c 688.3 -14.0 646.7 -29.0 602.0 -29.0 c 560.0 -29.0 527.5 -13.8 504.5 16.5 c 481.5 46.8 466.3 95.0 459.0 161.0 c 239 161 l 234.3 143.0 232.0 126.0 232.0 110.0 c 232.0 90.7 233.7 73.7 237.0 59.0 c 240.3 44.3 245.7 30.0 253.0 16.0 c 234.3 2.7 212.3 -8.2 187.0 -16.5 c 161.7 -24.8 137.0 -29.0 113.0 -29.0 c 82.3 -29.0 59.2 -20.7 43.5 -4.0 c 27.8 12.7 20.0 37.0 20.0 69.0 c 20.0 110.3 34.5 167.2 63.5 239.5 c 92.5 311.8 146.0 424.3 224.0 577.0 c 191 662 l 228.3 684.7 262.3 700.8 293.0 710.5 c 323.7 720.2 357.0 725.0 393.0 725.0 c 431.0 725.0 458.3 716.7 475.0 700.0 c 506.3 716.7 534.3 725.0 559.0 725.0 c 595.7 725.0 622.3 713.3 639.0 690.0 c 655.7 666.7 664.0 629.3 664.0 578.0 c h 453 280 m 453 292 l 453.0 416.0 455.0 516.3 459.0 593.0 c 447 593 l 373.7 477.0 317.7 372.7 279.0 280.0 c h'),
}

_LEMONADA_CAP = 726          # height of the capital letters in those units
_BINGO_SIZE = 24             # pt: cap height is 24 * 0.726 = 17.4 pt


# ---------------------------------------------------------------- songs
def clean_theme_name(raw: Any) -> str:
    """The round / theme name as printed above BINGO. Unlike a song title it keeps "(2024)" style tags."""
    s = "" if raw is None else str(raw)
    s = s.replace("\u00a0", " ").replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", " ", s.replace('"', " ")).strip()


def clean_title(raw: Any) -> str:
    """A song title as it should print: no quote marks, no note symbols, no "(1985)" year tags, no stray spaces."""
    s = "" if raw is None else str(raw)
    s = (s.replace("\u00a0", " ").replace("\u2019", "'").replace("\u2018", "'")
          .replace("\u201c", '"').replace("\u201d", '"').replace("\ufffd", ""))
    s = re.sub("[\u266a\u266b\u2669\u266c]", " ", s)                       # music note symbols
    s = re.sub(r"\s*\((?:19|20)\d{2}\)\s*$", "", s.strip())                    # a trailing "(1985)"
    s = s.replace('"', " ")                                                   # quote marks anywhere
    s = re.sub(r"\s+", " ", s).strip(" \t-\u2013\u2014,;:")
    if s.startswith("'") and s.endswith("'") and len(s) > 2 and s.count("'") == 2:
        s = s[1:-1].strip()
    return s


def unique_titles(songs: Sequence[Dict[str, Any]]) -> List[str]:
    """Distinct, printable titles from a theme's song list (case-insensitive), in list order."""
    seen, out = set(), []
    for s in songs:
        t = clean_title(s.get("title") if isinstance(s, dict) else s)
        key = re.sub(r"[^a-z0-9]+", "", t.lower())
        if not t or not key or t.startswith("=") or t in ("#VALUE!", "#REF!") or key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def make_cards(titles: Sequence[str], count: int, rng: Optional[random.Random] = None) -> List[List[List[Optional[str]]]]:
    """`count` cards. Each card is 5 rows x 5 columns; the centre square is None (free space).
    Every card holds 24 DIFFERENT titles; no two cards are identical."""
    rng = rng or random.Random()
    titles = list(titles)
    if len(titles) < MIN_SONGS:
        raise ValueError("need_%d_songs" % MIN_SONGS)
    count = max(1, min(int(count), MAX_CARDS))
    cards, seen = [], set()
    attempts = 0
    while len(cards) < count:
        attempts += 1
        pick = rng.sample(titles, MIN_SONGS)
        key = tuple(pick)
        if key in seen and attempts < count * 20 and len(titles) > MIN_SONGS:
            continue                      # a repeated card: try again (only possible with a small list)
        seen.add(key)
        it = iter(pick)
        grid = [[None if (r, c) == FREE_SPACE else next(it) for c in range(5)] for r in range(5)]
        cards.append(grid)
    return cards


# ---------------------------------------------------------------- text
def _text_width(s: str, size: float) -> float:
    total = 0
    for ch in s:
        try:
            code = ch.encode("cp1252")[0]
        except UnicodeEncodeError:
            code = 63
        total += _W[code - 32] if 32 <= code <= 255 else 556
    return total * size / 1000.0


def wrap_text(s: str, size: float, max_w: float) -> List[str]:
    """Break a title into lines that fit max_w points (words are never split unless one word is too long)."""
    words, lines, cur = s.split(" "), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if _text_width(trial, size) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:                      # a single very long word: cut it
        while _text_width(ln, size) > max_w and len(ln) > 1:
            k = len(ln)
            while k > 1 and _text_width(ln[:k], size) > max_w:
                k -= 1
            out.append(ln[:k]); ln = ln[k:]
        out.append(ln)
    return out


def _splits_word(lines: List[str], title: str) -> bool:
    """True when wrapping had to cut inside a word (the number of printed words grew)."""
    return sum(len(l.split(" ")) for l in lines) != len(title.split(" "))


def fit_title(s: str, max_w: float = CELL_W - 3, max_h: float = CELL_H - 6):
    """Largest font (11 down to 4.5 pt) at which the whole title fits in a square WITHOUT breaking a word.
    Returns (size, lines)."""
    size = 10.5
    while size >= 4.5:
        lines = wrap_text(s, size, max_w)
        if len(lines) * size * 1.12 <= max_h and not _splits_word(lines, s):
            return size, lines
        size -= 0.25
    return 4.5, wrap_text(s, 4.5, max_w)


def _pdf_str(s: str) -> bytes:
    b = s.encode("cp1252", errors="replace")
    return b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


# ---------------------------------------------------------------- pdf
def _card_ops(grid, x0: float, top: float, title: str) -> List[bytes]:
    """Drawing instructions for one card. x0 = left edge, top = distance from the top of the page."""
    ops: List[bytes] = []
    y_top = PAGE_H - top                  # PDF y grows upwards
    # header band
    ops.append(("%.3f %.3f %.3f rg %.2f %.2f %.2f %.2f re f" % (*HEADER_FILL, x0, y_top - HEADER_H, CARD_W, HEADER_H)).encode())
    # the round / theme name across the top, centred above BINGO, in the same font and size as the song titles
    name = clean_theme_name(title)
    if name:
        size, lines = fit_title(name, max_w=CARD_W - 16, max_h=14)
        size = min(size, 10.5)
        ops.append(b"0 0 0 rg")
        wn = _text_width(name, size)
        ops.append(b"BT /F1 %.1f Tf %.2f %.2f Td (%s) Tj ET" % (size, x0 + CARD_W / 2 - wn / 2, y_top - 12.5, _pdf_str(name)))
    # BINGO in Lemonada Bold, one letter centred in each column, sitting in the lower part of the header
    ops.append(b"0 0 0 rg")
    k = _BINGO_SIZE / 1000.0
    base_y = y_top - HEADER_H + 11        # baseline; the G's tail swings below it, still inside the header
    for i, ch in enumerate("BINGO"):
        adv, path = _LEMONADA_BINGO[ch]
        cx = x0 + CELL_W * i + CELL_W / 2 - adv * k / 2
        ops.append(b"q %.5f 0 0 %.5f %.2f %.2f cm" % (k, k, cx, base_y))
        ops.append(path.encode() + b" f")
        ops.append(b"Q")
    # free space
    fr, fc = FREE_SPACE
    fx, fy = x0 + CELL_W * fc, y_top - HEADER_H - CELL_H * (fr + 1)
    ops.append(("%.3f %.3f %.3f rg %.2f %.2f %.2f %.2f re f" % (*FREE_FILL, fx, fy, CELL_W, CELL_H)).encode())
    lw = min(CELL_W, CELL_H) - 6
    ops.append(("q %.2f 0 0 %.2f %.2f %.2f cm /Logo Do Q" % (lw, lw, fx + (CELL_W - lw) / 2, fy + (CELL_H - lw) / 2)).encode())
    # song titles
    ops.append(b"0 0 0 rg")
    for r in range(5):
        for c in range(5):
            t = grid[r][c]
            if not t:
                continue
            size, lines = fit_title(t)
            lead = size * 1.15
            block = lead * len(lines)
            cy = y_top - HEADER_H - CELL_H * r - CELL_H / 2
            y = cy + block / 2 - size * 0.85
            for ln in lines:
                wln = _text_width(ln, size)
                x = x0 + CELL_W * c + CELL_W / 2 - wln / 2
                ops.append(b"BT /F1 %.1f Tf %.2f %.2f Td (%s) Tj ET" % (size, x, y, _pdf_str(ln)))
                y -= lead
    # grid lines
    ops.append(b"0 0 0 RG 0.75 w")
    total_h = HEADER_H + CELL_H * 5
    for i in range(6):
        y = y_top - HEADER_H - CELL_H * i
        ops.append(("%.2f %.2f m %.2f %.2f l S" % (x0, y, x0 + CARD_W, y)).encode())
    for i in range(6):
        x = x0 + CELL_W * i
        ops.append(("%.2f %.2f m %.2f %.2f l S" % (x, y_top - HEADER_H - CELL_H * 5, x, y_top - HEADER_H)).encode())
    ops.append(b"1.5 w")
    ops.append(("%.2f %.2f %.2f %.2f re S" % (x0, y_top - total_h, CARD_W, total_h)).encode())
    ops.append(("%.2f %.2f m %.2f %.2f l S" % (x0, y_top - HEADER_H, x0 + CARD_W, y_top - HEADER_H)).encode())
    return ops


def _cut_lines() -> List[bytes]:
    """Dashed line between the two card rows, like the sample."""
    y = PAGE_H - (CARD_TOP[0] + HEADER_H + CELL_H * 5 + (CARD_TOP[1] - (CARD_TOP[0] + HEADER_H + CELL_H * 5)) / 2)
    return [b"q 0.2 0.45 0.6 RG 0.8 w [4 3] 0 d", ("%.2f %.2f m %.2f %.2f l S Q" % (12, y, 600, y)).encode()]


def build_pdf(cards: Sequence[Sequence[Sequence[Optional[str]]]], title: str = "") -> bytes:
    """A complete PDF (4 cards per page). `cards` come from make_cards()."""
    pages = max(1, math.ceil(len(cards) / CARDS_PER_PAGE))
    objs: List[bytes] = []                # index i -> object number i+1

    def add(b: bytes) -> int:
        objs.append(b)
        return len(objs)

    rgb, alpha = zlib.decompress(base64.b64decode(_LOGO_RGB)), zlib.decompress(base64.b64decode(_LOGO_ALPHA))
    catalog = add(b"")                    # 1 (filled later)
    pages_obj = add(b"")                  # 2
    f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    smask_c = zlib.compress(alpha, 9)
    smask = add(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n" % (_LOGO_PX, _LOGO_PX, len(smask_c)) + smask_c + b"\nendstream")
    img_c = zlib.compress(rgb, 9)
    logo = add(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB /BitsPerComponent 8 /SMask %d 0 R /Filter /FlateDecode /Length %d >>\nstream\n" % (_LOGO_PX, _LOGO_PX, smask, len(img_c)) + img_c + b"\nendstream")
    page_ids = []
    for p in range(pages):
        ops: List[bytes] = []
        chunk = cards[p * CARDS_PER_PAGE:(p + 1) * CARDS_PER_PAGE]
        for i, grid in enumerate(chunk):
            ops += _card_ops(grid, CARD_X[i % 2], CARD_TOP[i // 2], title)
        ops += _cut_lines()
        body = zlib.compress(b"\n".join(ops), 9)
        content = add(b"<< /Filter /FlateDecode /Length %d >>\nstream\n" % len(body) + body + b"\nendstream")
        page = add(("<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R /Resources << /Font << /F1 %d 0 R >> /XObject << /Logo %d 0 R >> >> >>"
                    % (pages_obj, PAGE_W, PAGE_H, content, f1, logo)).encode())
        page_ids.append(page)
    objs[catalog - 1] = ("<< /Type /Catalog /Pages %d 0 R >>" % pages_obj).encode()
    kids = " ".join("%d 0 R" % i for i in page_ids)
    objs[pages_obj - 1] = ("<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(page_ids))).encode()
    out = bytearray(b"%PDF-1.4\n%\\xe2\\xe3\\xcf\\xd3\n")
    offsets = []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % n + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, catalog, xref)
    return bytes(out)


def generate_pdf(songs: Sequence[Dict[str, Any]], count: int, theme: str = "", rng: Optional[random.Random] = None) -> Dict[str, Any]:
    """songs = a theme's parsed song list. Returns {pdf, cards, pages, songs_used}. Raises ValueError('need_24_songs')."""
    titles = unique_titles(songs)
    if len(titles) < MIN_SONGS:
        raise ValueError("need_%d_songs" % MIN_SONGS)
    n = max(1, min(int(count or 1), MAX_CARDS))
    n += (-n) % CARDS_PER_PAGE            # fill the last page (4 per sheet)
    cards = make_cards(titles, n, rng)
    return {"pdf": build_pdf(cards, theme), "cards": len(cards), "pages": math.ceil(len(cards) / CARDS_PER_PAGE),
            "songs_used": len(titles)}


# ================================================================ alpha.110: LOTERIA (picture) cards
def is_loteria(theme: Any) -> bool:
    """Any round with "Loteria" (or "Lotería") in its name plays with pictures instead of words."""
    t = "" if theme is None else str(theme)
    t = t.replace("\u00ed", "i").replace("\u00cd", "I")
    return "loteria" in t.lower()


def loteria_type(theme: Any) -> str:
    """The type shown above LOTERIA: "Bad Bunny Loteria" -> "Bad Bunny"; plain "Loteria" -> "" (nothing to add)."""
    t = clean_theme_name(theme).replace("\u00ed", "i").replace("\u00cd", "I")
    t = re.sub(r"(?i)\bloteria\b", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" -_:,.()")
    return t


def _pic_sort_key(name: str):
    """Pictures in number order when they start with a number (01_x.png, 2.jpg), otherwise by name."""
    m = re.match(r"^\s*(\d+)", name)
    return (0, int(m.group(1)), name.lower()) if m else (1, 0, name.lower())


def loteria_images(cards_folder: Any) -> List[str]:
    """Full paths of the pictures in a theme's Cards folder (png / jpg / webp / bmp / gif), in number-then-name order."""
    from pathlib import Path
    try:
        folder = Path(cards_folder)
        files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in IMG_EXTS and not f.name.startswith((".", "~"))]
    except (OSError, TypeError, ValueError):
        return []
    files.sort(key=lambda f: _pic_sort_key(f.name))
    return [str(f) for f in files]


def make_loteria_cards(images: Sequence[str], count: int, rng: Optional[random.Random] = None) -> List[List[List[str]]]:
    """`count` cards, each 4 x 4 = 16 DIFFERENT pictures, no free space. Raises ValueError('need_16_pictures')."""
    rng = rng or random.Random()
    imgs = list(dict.fromkeys(images))
    if len(imgs) < LOTERIA_PICS:
        raise ValueError("need_%d_pictures" % LOTERIA_PICS)
    count = max(1, min(int(count), MAX_CARDS))
    cards, seen, attempts = [], set(), 0
    while len(cards) < count:
        attempts += 1
        pick = rng.sample(imgs, LOTERIA_PICS)
        key = tuple(pick)
        if key in seen and attempts < count * 20 and len(imgs) > LOTERIA_PICS:
            continue
        seen.add(key)
        it = iter(pick)
        cards.append([[next(it) for _ in range(LOTERIA_GRID)] for _ in range(LOTERIA_GRID)])
    return cards


def _prepare_picture(path: str):
    """Read a picture with Pillow, flatten transparency onto white and shrink it. Returns (width, height, jpeg bytes) or None."""
    try:
        from PIL import Image, ImageOps
        import io
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGBA")
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[-1])
                im = bg
            else:
                im = im.convert("RGB")
            im.thumbnail(LOTERIA_PX)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=88)
            return im.width, im.height, buf.getvalue()
    except Exception:
        return None


def _glyph_run(text: str, size: float, x_center: float, base_y: float) -> List[bytes]:
    """Lemonada Bold letters as vector paths, centred on x_center. Only the letters we carry (B I N G O L T E R A)."""
    table = dict(_LEMONADA_BINGO)
    table.update(_LEMONADA_EXTRA)
    k = size / 1000.0
    adv_total = sum(table[c][0] for c in text) * k + 0.28 * size * (len(text) - 1)     # a little air between letters
    x = x_center - adv_total / 2
    out: List[bytes] = []
    for c in text:
        adv, path = table[c]
        out.append(b"q %.5f 0 0 %.5f %.2f %.2f cm" % (k, k, x, base_y))
        out.append(path.encode() + b" f")
        out.append(b"Q")
        x += adv * k + 0.28 * size
    return out


LOTERIA_HEADER_H = 56
LOTERIA_CARD_W = 360                       # two cards of 360 pt + a 36 pt gap (the cut line sits in the middle of it) fit a 792 pt page
LOTERIA_X = (18, 414)
LOTERIA_TOP = 22
LOTERIA_CELL_W = LOTERIA_CARD_W / LOTERIA_GRID     # 90 pt
LOTERIA_CELL_H = 128.0                              # portrait cells (the pictures are portrait), so the art fills the square


def _loteria_card_ops(grid, names: Dict[str, str], x0: float, top: float, type_name: str) -> List[bytes]:
    ops: List[bytes] = []
    y_top = LOTERIA_PAGE_H - top
    ops.append(("%.3f %.3f %.3f rg %.2f %.2f %.2f %.2f re f" % (*HEADER_FILL, x0, y_top - LOTERIA_HEADER_H, LOTERIA_CARD_W, LOTERIA_HEADER_H)).encode())
    ops.append(b"0 0 0 rg")
    mid = x0 + LOTERIA_CARD_W / 2
    if type_name:
        size, _ = fit_title(type_name, max_w=LOTERIA_CARD_W - 20, max_h=14)
        size = min(size, 11.0)
        w = _text_width(type_name, size)
        ops.append(b"BT /F1 %.1f Tf %.2f %.2f Td (%s) Tj ET" % (size, mid - w / 2, y_top - 13, _pdf_str(type_name)))
        ops += _glyph_run("LOTERIA", 28, mid, y_top - LOTERIA_HEADER_H + 11)
    else:
        ops += _glyph_run("LOTERIA", 30, mid, y_top - LOTERIA_HEADER_H / 2 - 10)
    pad = 2.0
    for r in range(LOTERIA_GRID):
        for c in range(LOTERIA_GRID):
            res = names.get(grid[r][c])
            if not res:
                continue
            cx = x0 + LOTERIA_CELL_W * c
            cy = y_top - LOTERIA_HEADER_H - LOTERIA_CELL_H * (r + 1)
            iw, ih = names["__size__" + res]
            sc = min((LOTERIA_CELL_W - 2 * pad) / iw, (LOTERIA_CELL_H - 2 * pad) / ih)
            w, h = iw * sc, ih * sc
            ops.append(("q %.2f 0 0 %.2f %.2f %.2f cm /%s Do Q" % (w, h, cx + (LOTERIA_CELL_W - w) / 2, cy + (LOTERIA_CELL_H - h) / 2, res)).encode())
    ops.append(b"0 0 0 RG 0.75 w")
    total_h = LOTERIA_HEADER_H + LOTERIA_CELL_H * LOTERIA_GRID
    for i in range(LOTERIA_GRID + 1):
        y = y_top - LOTERIA_HEADER_H - LOTERIA_CELL_H * i
        ops.append(("%.2f %.2f m %.2f %.2f l S" % (x0, y, x0 + LOTERIA_CARD_W, y)).encode())
        x = x0 + LOTERIA_CELL_W * i
        ops.append(("%.2f %.2f m %.2f %.2f l S" % (x, y_top - total_h, x, y_top - LOTERIA_HEADER_H)).encode())
    ops.append(b"1.5 w")
    ops.append(("%.2f %.2f %.2f %.2f re S" % (x0, y_top - total_h, LOTERIA_CARD_W, total_h)).encode())
    ops.append(("%.2f %.2f m %.2f %.2f l S" % (x0, y_top - LOTERIA_HEADER_H, x0 + LOTERIA_CARD_W, y_top - LOTERIA_HEADER_H)).encode())
    return ops


def _cut_lines_loteria() -> List[bytes]:
    """The dashed line straight down the middle of the page, between the two cards, so the host knows where to cut."""
    x = LOTERIA_PAGE_W / 2.0
    return [b"q 0.2 0.45 0.6 RG 0.8 w [4 3] 0 d", ("%.2f %.2f m %.2f %.2f l S Q" % (x, 8, x, LOTERIA_PAGE_H - 8)).encode()]


def build_loteria_pdf(cards: Sequence[Sequence[Sequence[str]]], type_name: str = "") -> bytes:
    """A PDF of picture cards, 2 per landscape page. Every picture is stored ONCE and drawn wherever it is used."""
    pages = max(1, math.ceil(len(cards) / LOTERIA_PER_PAGE))
    paths = list(dict.fromkeys(p for g in cards for row in g for p in row))
    prepared = {}
    for p in paths:
        pic = _prepare_picture(p)
        if pic:
            prepared[p] = pic
    objs: List[bytes] = []

    def add(b: bytes) -> int:
        objs.append(b)
        return len(objs)

    catalog, pages_obj = add(b""), add(b"")
    f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    res_of, names = {}, {}
    for i, (p, (w, h, data)) in enumerate(prepared.items()):
        oid = add(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length %d >>\nstream\n" % (w, h, len(data)) + data + b"\nendstream")
        res = "Im%d" % i
        res_of[res] = oid
        names[p] = res
        names["__size__" + res] = (w, h)
    xobj = " ".join("/%s %d 0 R" % (r, o) for r, o in res_of.items())
    page_ids = []
    for pg in range(pages):
        ops: List[bytes] = []
        for i, grid in enumerate(cards[pg * LOTERIA_PER_PAGE:(pg + 1) * LOTERIA_PER_PAGE]):
            ops += _loteria_card_ops(grid, names, LOTERIA_X[i], LOTERIA_TOP, type_name)
        ops += _cut_lines_loteria()
        body = zlib.compress(b"\n".join(ops), 9)
        content = add(b"<< /Filter /FlateDecode /Length %d >>\nstream\n" % len(body) + body + b"\nendstream")
        page_ids.append(add(("<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R /Resources << /Font << /F1 %d 0 R >> /XObject << %s >> >> >>"
                             % (pages_obj, LOTERIA_PAGE_W, LOTERIA_PAGE_H, content, f1, xobj)).encode()))
    objs[catalog - 1] = ("<< /Type /Catalog /Pages %d 0 R >>" % pages_obj).encode()
    objs[pages_obj - 1] = ("<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join("%d 0 R" % i for i in page_ids), len(page_ids))).encode()
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % n + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, catalog, xref)
    return bytes(out)


def generate_loteria_pdf(cards_folder: Any, count: int, theme: str = "", rng: Optional[random.Random] = None) -> Dict[str, Any]:
    """Picture cards from a theme's Cards folder. Raises ValueError('need_16_pictures')."""
    images = loteria_images(cards_folder)
    usable = [p for p in images if _prepare_picture(p)]
    if len(usable) < LOTERIA_PICS:
        raise ValueError("need_%d_pictures" % LOTERIA_PICS)
    n = max(1, min(int(count or 1), MAX_CARDS))
    n += (-n) % LOTERIA_PER_PAGE
    cards = make_loteria_cards(usable, n, rng)
    return {"pdf": build_loteria_pdf(cards, loteria_type(theme)), "cards": len(cards), "pages": math.ceil(len(cards) / LOTERIA_PER_PAGE),
            "songs_used": len(usable)}
