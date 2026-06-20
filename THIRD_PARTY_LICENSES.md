# Drittanbieter-Lizenzen

Das ausgelieferte AppImage von **Axis IP Utility** bündelt die unten
aufgeführten Komponenten. Der eigene Programmcode (`axis_discovery_cli.py`,
`axis_discovery_gui.py`, `bump_version.py`, `build_appimage.sh`) steht unter der
**GPL-3.0-or-later** (siehe `LICENSE`) und ist von den folgenden Lizenzen nicht
betroffen.

## Übersicht

| Komponente | Version | Lizenz |
|---|---|---|
| CPython | 3.13.14 | PSF License Agreement |
| Tcl | 9.0.3 | Tcl/Tk License (BSD-artig) |
| Tk | 9.0.3 | Tcl/Tk License (BSD-artig) |
| libffi | 3.6.0 | libffi License (MIT-artig) |
| zeroconf | 0.149.16 | **LGPL-2.1-or-later** |
| ifaddr | 0.2.0 | MIT |
| prettytable | 3.17.0 | BSD-3-Clause |
| wcwidth | 0.8.1 | MIT |

> **Hinweis zu zeroconf (LGPL-2.1-or-later):** Alle übrigen Komponenten sind
> permissiv lizenziert. `zeroconf` steht unter der LGPL (schwaches Copyleft).
> Beim Verteilen des AppImage muss der LGPL-Lizenztext beiliegen und es muss
> möglich sein, `zeroconf` durch eine eigene Version zu ersetzen – beim AppImage
> ist das über `./AxisDiscovery-x86_64.AppImage --appimage-extract`, Austausch
> der Dateien und erneutes Packen gegeben. Der Quellcode ist erhältlich unter
> https://github.com/python-zeroconf/python-zeroconf .

---

## CPython 3.13.14

Copyright © 2001-2024 Python Software Foundation. Alle Rechte vorbehalten.

Lizenziert unter dem **PSF License Agreement** (BSD-kompatibel, permissiv).
Vollständiger Text: https://docs.python.org/3/license.html
(im AppImage zusätzlich unter `usr/lib/python3.13/LICENSE.txt`, falls vorhanden).

---

## Tcl 9.0.3 und Tk 9.0.3

This software is copyrighted by the Regents of the University of
California, Sun Microsystems, Inc., Scriptics Corporation, ActiveState
Corporation, Apple Inc. and other parties.  The following terms apply to all
files associated with the software unless explicitly disclaimed in
individual files.

The authors hereby grant permission to use, copy, modify, distribute,
and license this software and its documentation for any purpose, provided
that existing copyright notices are retained in all copies and that this
notice is included verbatim in any distributions. No written agreement,
license, or royalty fee is required for any of the authorized uses.
Modifications to this software may be copyrighted by their authors
and need not follow the licensing terms described here, provided that
the new terms are clearly indicated on the first page of each file where
they apply.

IN NO EVENT SHALL THE AUTHORS OR DISTRIBUTORS BE LIABLE TO ANY PARTY
FOR DIRECT, INDIRECT, SPECIAL, INCIDENTAL, OR CONSEQUENTIAL DAMAGES
ARISING OUT OF THE USE OF THIS SOFTWARE, ITS DOCUMENTATION, OR ANY
DERIVATIVES THEREOF, EVEN IF THE AUTHORS HAVE BEEN ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.

THE AUTHORS AND DISTRIBUTORS SPECIFICALLY DISCLAIM ANY WARRANTIES,
INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE, AND NON-INFRINGEMENT.  THIS SOFTWARE
IS PROVIDED ON AN "AS IS" BASIS, AND THE AUTHORS AND DISTRIBUTORS HAVE
NO OBLIGATION TO PROVIDE MAINTENANCE, SUPPORT, UPDATES, ENHANCEMENTS, OR
MODIFICATIONS.

---

## libffi 3.6.0

libffi - Copyright (c) 1996-2024  Anthony Green, Red Hat, Inc and others.
See source files for details.

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
``Software''), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED ``AS IS'', WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

---

## zeroconf 0.149.16

Copyright © 2003 Paul Scott-Murphy, 2014 William McBrine, Jakub Stasiak und
weitere Mitwirkende.

Lizenziert unter der **GNU Lesser General Public License, Version 2.1 oder
später (LGPL-2.1-or-later)**. Der vollständige Lizenztext ist erhältlich unter
https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html .
Quellcode: https://github.com/python-zeroconf/python-zeroconf

---

## ifaddr 0.2.0

Copyright © 2014 Stefan C. Müller.

Lizenziert unter der **MIT-Lizenz**:

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN
AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

---

## prettytable 3.17.0

Copyright © 2009 Luke Maurits und weitere Mitwirkende.

Lizenziert unter der **BSD-3-Clause-Lizenz**. Weiterverbreitung in Quell- und
Binärform, mit oder ohne Änderungen, ist gestattet, sofern Copyright-Hinweis,
Bedingungsliste und Haftungsausschluss erhalten bleiben und weder Name noch
Namen der Mitwirkenden ohne vorherige schriftliche Genehmigung zur Bewerbung
abgeleiteter Produkte verwendet werden. Die Software wird „AS IS" ohne jegliche
Gewährleistung bereitgestellt.
Quellcode: https://github.com/prettytable/prettytable

---

## wcwidth 0.8.1

Copyright © Jeff Quast.

Lizenziert unter der **MIT-Lizenz** (Wortlaut wie bei *ifaddr* oben).
Quellcode: https://github.com/jquast/wcwidth
