# Release license collection

The collector includes installed runtime license/NOTICE files and the build
Python's license. Development-only dependencies are excluded.

## mft 0.6.1

The [release metadata](https://github.com/omerbenamram/pymft-rs/blob/13b4790e325ea282ba885e0672d339ca3cf8acbc/pyproject.toml) explicitly declares MIT.
The release repository tree and wheel contain no license text or copyright notice
(checked 2026-09-18). `LICENSES/mft-0.6.1.txt` therefore supplies the standard
MIT text, upstream declaration, source and author attribution. Template copyright
placeholders remain unfilled; they are not presented as an upstream notice.

The collector uses this material only for mft 0.6.1 when the installed
package has no license files. Installed license files take precedence. Other
missing licenses still produce an error. Embedded native dependencies are not
fully audited by this collector.
