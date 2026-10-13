# Runtime performance

Target Linux-visible RAM is about 36 MiB.

With the browser live view closed, one runtime snapshot showed approximately:

- RAM total: ~36.4 MiB
- real used: ~14.2 MiB
- buff/cache: ~17.5 MiB
- CPU idle: ~90.8%
- prudynt RSS: ~6.7 MiB

Earlier, with live web video open, `uhttpd`, `prudynt`, and the local HTTP/curl proxy path consumed noticeably more CPU. After leaving the web page, CPU load fell sharply.

## Interpretation

- The SoC is not permanently CPU-saturated.
- BusyBox `top` includes reclaimable page cache in "used".
- The current browser streaming/proxy path is a major optimization target.
- Load average may remain elevated for minutes after instantaneous CPU usage falls.

For quick diagnostics use:

```sh
./tools/runtime-snapshot.sh
```
