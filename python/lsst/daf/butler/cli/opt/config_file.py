# This file is part of daf_butler.
#
# Developed for the LSST Data Management System.
# This product includes software developed by the LSST Project
# (http://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import click


class config_file_option:  # noqa: N801

    defaultHelp = "Path to a pex config override to be included after the Instrument config overrides are " \
                  "applied."

    def __init__(self, required=False, help=defaultHelp):
        self.required = required
        self.help = help

    def __call__(self, f):
        return click.option("-C", "--config-file",
                            required=self.required,
                            type=click.STRING,
                            help=self.help)(f)
