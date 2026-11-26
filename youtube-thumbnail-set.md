# youtube-thumbnail-set

Sets a custom thumbnail on many YouTube videos from a folder of JPEGs. It changes
public pages, so a run needs `--yes`.

```sh
python3 youtube-thumbnail-set --map map.json --dry-run --dir final
python3 youtube-thumbnail-set --map map.json --dir final --yes
python3 youtube-thumbnail-set --map map.json --dir final --yes --only VIDEO_ID
```

`map.json` is a list of `{"item": 3, "video": "<id>"}`. The image for each entry is
`final/03-<id>.jpg`. Auth is `YOUTUBE_ACCESS_TOKEN`, or `YOUTUBE_CLIENT_ID`,
`YOUTUBE_CLIENT_SECRET` and `YOUTUBE_REFRESH_TOKEN` (refreshed by the tool).

- The `youtube.upload` scope is enough for `thumbnails.set`. It cannot change titles
  or privacy: that needs the broader `youtube` scope.
- A private video accepts a thumbnail. The channel must be verified.
- The run stops at the first 401 or 403, because a scope or quota error repeats on
  every video. Other errors are reported and the run goes on (exit 1 at the end).
- Open the videos in Studio once to confirm: the API reports success before
  the picture shows.

Test: `python3 youtube-thumbnail-set.test.py` runs against a local fake API.
