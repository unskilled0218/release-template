# Platform preparation

- [Platform preparation](#platform-preparation)
  - [Install AMD64 and ARM64 emulation](#install-amd64-and-arm64-emulation)
  - [Verify runtime support](#verify-runtime-support)

## Install AMD64 and ARM64 emulation

An authorized host administrator must run these commands before the two-platform release test:

```sh
docker run --privileged --rm tonistiigi/binfmt --install amd64,arm64
docker buildx inspect --bootstrap
```

The first command registers emulation handlers in the Docker daemon host's kernel. It requires privileged access and changes host configuration; it is not an ordinary application container. Verify the selected Docker context before running it. The release tool and coding agent do not run this privileged setup automatically.

The builder's advertised platforms should include `linux/amd64` and `linux/arm64`. If builder nodes or runtime daemons use different hosts, prepare each host that needs emulation, or use native nodes for the required architecture. Registering handlers on one host does not configure every remote builder or daemon. Recheck support after host restarts or environment changes.

## Verify runtime support

Builder advertising alone does not prove that containers can execute. On the Docker context used for runtime verification, run:

```sh
docker run --rm --platform linux/amd64 ubuntu:24.04 echo "Hello World"
docker run --rm --platform linux/arm64 ubuntu:24.04 echo "Hello World"
```

Both commands must exit successfully and print `Hello World`. They may pull Ubuntu images. These checks verify architecture execution only; they do not verify the release fixture's default command, registry publication, digest promotion, or cleanup safety. Follow the release test's separate checks for those outcomes.
