# Platform preparation

- [Platform preparation](#platform-preparation)
  - [Install AMD64 and ARM64 emulation](#install-amd64-and-arm64-emulation)
  - [Verify runtime support](#verify-runtime-support)

## Install AMD64 and ARM64 emulation

Prefer native platform nodes. Only an authorized host administrator may run this optional emulation setup on hosts that need it.

First check tools, Docker context, and builder access using the [release checklist](release-process.md#check-platform-readiness). Emulation setup does not fix connectivity.

```sh
docker run --privileged --rm tonistiigi/binfmt --install amd64,arm64
docker buildx inspect --bootstrap
```

The first command changes the selected daemon host's kernel handlers and requires privileged access. Verify the host first. Neither the release tool nor the coding agent runs it automatically.

The builder must advertise `linux/amd64` and `linux/arm64`. Prepare each builder/runtime host that needs emulation; one host's setup does not configure others. Recheck after restarts or environment changes.

## Verify runtime support

Advertising alone does not prove execution. With separate approval, run on the intended runtime context:

```sh
docker run --rm --platform linux/amd64 ubuntu:24.04 echo "Hello World"
docker run --rm --platform linux/arm64 ubuntu:24.04 echo "Hello World"
```

Both commands must exit zero and print `Hello World`; they may pull Ubuntu images. They check architecture execution, not this project's image or publication. See [image usage](image-usage.md) and [verification limits](verification.md).
