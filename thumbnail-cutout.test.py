#!/usr/bin/env python3
"""E2E for thumbnail-cutout on synthetic photos (needs opencv-python, SKIPs without it).

A flat blue background with a red disc: alpha must be 255 at the centre and 0 at the
corners, and the disc colour must stay red. A disc with a hole of background inside
(like a gap between an arm and the body): the hole must be transparent too. A soft shadow on one side must pass and vanish; a medium one must fail, not leave a slab. A failed write and a .jpg name exit 2. A noisy
background must fail with exit 1 and write no file. A flat picture with nothing on it
must fail (the cutout keeps 0 percent). An unreadable file exits 2.
Prints one evidence JSON line.
"""
import json, subprocess, sys, tempfile
from pathlib import Path

try:
    import cv2, numpy as np
except ImportError:
    print(json.dumps({'test': 'thumbnail-cutout', 'ok': None, 'skip': 'no opencv'}))
    sys.exit(0)

TOOL = str(Path(__file__).parent / 'thumbnail-cutout')


def run(*a):
    p = subprocess.run([sys.executable, TOOL, *a], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def main():
    d = Path(tempfile.mkdtemp())
    flat = np.full((400, 600, 3), (200, 90, 20), np.uint8)               # BGR blue
    disc = flat.copy()
    cv2.circle(disc, (300, 200), 120, (30, 30, 220), -1)                  # red disc
    cv2.imwrite(str(d / 'disc.png'), disc)
    rc, out, err = run(str(d / 'disc.png'), str(d / 'o.png'))
    assert rc == 0, err
    o = cv2.imread(str(d / 'o.png'), cv2.IMREAD_UNCHANGED)
    assert o.shape[2] == 4 and o[200, 300, 3] == 255 and o[5, 5, 3] == 0 and o[395, 595, 3] == 0
    assert o[200, 300, 2] > 180 and o[200, 300, 0] < 80                   # still red

    hole = disc.copy()
    cv2.circle(hole, (300, 200), 50, (200, 90, 20), -1)                   # background seen through the shape
    cv2.imwrite(str(d / 'hole.png'), hole)
    rc, _, err = run(str(d / 'hole.png'), str(d / 'h.png'))
    h = cv2.imread(str(d / 'h.png'), cv2.IMREAD_UNCHANGED)
    assert rc == 0 and h[200, 300, 3] == 0 and h[200, 400, 3] == 255, err

    noisy = np.random.RandomState(1).randint(0, 255, (400, 600, 3)).astype(np.uint8)
    cv2.imwrite(str(d / 'noisy.png'), noisy)
    rc, _, err = run(str(d / 'noisy.png'), str(d / 'n.png'))
    assert rc == 1 and 'flat colour' in err and not (d / 'n.png').exists()

    shade = disc.copy()
    shade[:, 450:] = (shade[:, 450:] * 0.9).astype(np.uint8)              # a soft shadow on one side
    cv2.imwrite(str(d / 'shade.png'), shade)
    rc, _, err = run(str(d / 'shade.png'), str(d / 's.png'))
    assert rc == 0, err
    s = cv2.imread(str(d / 's.png'), cv2.IMREAD_UNCHANGED)
    assert s[50, 550, 3] == 0                                             # the shadow is gone
    deep = disc.copy()
    deep[:, 450:] = (deep[:, 450:] * 0.8).astype(np.uint8)                # a medium shadow: must not become a slab
    cv2.imwrite(str(d / 'deep.png'), deep)
    rc, _, err = run(str(d / 'deep.png'), str(d / 'dp.png'))
    assert rc == 1 and 'shadow' in err and not (d / 'dp.png').exists(), (rc, err)
    rc, _, err = run(str(d / 'disc.png'), str(d / 'no-such-dir' / 'x.png'))     # failed write must not say ok
    assert rc == 2 and 'could not write' in err
    rc, _, err = run(str(d / 'disc.png'), str(d / 'o.jpg'))
    assert rc == 2 and '.png' in err and not (d / 'o.jpg').exists()

    edge = disc.copy()
    cv2.rectangle(edge, (0, 150), (60, 250), (30, 30, 220), -1)             # a person touching the side edge is fine
    cv2.imwrite(str(d / 'edge.png'), edge)
    rc, _, err = run(str(d / 'edge.png'), str(d / 'ed.png'))
    assert rc == 0, err

    cv2.imwrite(str(d / 'empty.png'), flat)
    rc, _, err = run(str(d / 'empty.png'), str(d / 'e.png'))
    assert rc == 1 and not (d / 'e.png').exists(), (rc, err)
    rc, _, err = run(str(d / 'missing.png'), str(d / 'm.png'))
    assert rc == 2
    print(json.dumps({'test': 'thumbnail-cutout', 'ok': True}))


if __name__ == '__main__':
    main()
