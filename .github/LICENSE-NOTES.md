# Release license collection

The collector includes installed runtime license/NOTICE files and the build
Python's license. Development-only dependencies are excluded.

## mft 0.7.0

The [tagged Python project metadata](https://github.com/omerbenamram/pymft-rs/blob/3266a8726a404947e799fd3e3c51042a8794f987/pyproject.toml) classifies the release as MIT. The tagged source tree and installed wheel contain no license text or copyright notice (checked 2026-10-12). `LICENSES/mft-0.7.0.txt` therefore supplies the standard MIT text, upstream declaration, source and author attribution. Template copyright placeholders remain unfilled; author metadata is not treated as a copyright notice.

The collector uses this material only for mft 0.7.0 when the installed
package has no license files. Installed license files take precedence. Other
missing licenses still produce an error. Embedded native dependencies are not
fully audited by this collector.
