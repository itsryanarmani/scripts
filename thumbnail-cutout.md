# thumbnail-cutout

Turns a photo of a person on a flat colour background into a transparent PNG for
thumbnail layouts. Needs `opencv-python` and `numpy`.

```sh
python3 thumbnail-cutout pose.jpg cut.png
python3 thumbnail-cutout pose.jpg cut.png --tolerance 18 --min-hole 4000
```

The background colour is the median of the border. Pixels near that colour that
join the border, or that form a large enclosed patch (the gap between an arm and
the body), become transparent. The edge gets a soft ramp, and the edge colour is
pulled away from the background to avoid a halo.

- It fails with a message when the border is not one flat colour, or when the cutout
  keeps under 5 or over 95 percent of the picture. It writes no file then. A soft
  shadow on one side of the wall is fine. A medium shadow fails
  (it would stay in the cutout as a slab). A person who touches the edge is fine.
- The output name must end in `.png`.
- A shadow on the floor or a vignette stays opaque: only the top and the sides of
  the photo are sampled. Light the backdrop evenly.
- A white shirt on a white background loses the shirt. Use a background colour that
  is not in the clothes.
- Raise `--tolerance` when a halo of background stays. Lower it when the edge of the
  hair is eaten.

Test: `python3 thumbnail-cutout.test.py` uses synthetic images (skips without opencv).
