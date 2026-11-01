# Cómo contribuir

Gracias por querer mejorar OpenFinance. Antes de nada, lee [AGENTS.md](AGENTS.md): reúne las reglas de arquitectura, dominio, seguridad y estilo del repositorio, y vale igual para personas que para agentes.

## Licencia

OpenFinance se distribuye bajo [AGPL-3.0-or-later](LICENSE) ([ADR-0008](docs/adr/0008-licencia-agpl.md)). Al contribuir, aceptas que tu contribución se publique bajo esa misma licencia. No hay CLA ni cesión de derechos, y los ficheros no llevan cabeceras de licencia.

## Firma tus commits (DCO)

Cada commit debe llevar una línea `Signed-off-by` con tu nombre y tu email reales:

```
Signed-off-by: Nombre Apellido <tu@email.example>
```

Git la añade por ti con `-s`:

```bash
git commit -s -m "feat: …"
```

Si olvidaste firmar el último commit: `git commit --amend -s --no-edit`. Para varios commits de tu rama: `git rebase --signoff main`.

Con esa línea certificas el Developer Certificate of Origin 1.1, cuyo texto original (<https://developercertificate.org/>) se reproduce sin cambios:

```
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.


Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

## Antes de abrir un pull request

- Referencia el ticket (`OF-xxx`) de [docs/product/roadmap.md](docs/product/roadmap.md) y actualiza su estado.
- Commits con [Conventional Commits](https://www.conventionalcommits.org/) y firmados (`-s`).
- `make check` en verde. Si cambias la API, ejecuta `make openapi`.
- Si añades una dependencia, `make licenses CHECK=1` debe seguir en verde. Si su licencia no está en la lista permitida, explica por qué es compatible y actualiza [docs/legal/dependencias.md](docs/legal/dependencias.md).
- No incluyas datos reales: ni extractos bancarios ni secretos.
