# Python ECM example scripts

## Introduction

The scripts in this folder demonstrate the use of Python 3 to control
WiRE using the Externally Controlled Measurement JSON-RPC API.

## Installation

This will require Python 3 (3.4 or higher) and the Pillow image
handling extension. One way to satisfy these requirements is
to setup [Chocolatey](http://chocolatey.org) then run:

    choco install python --confirm
    choco install pillow --source python --confirm
    choco install requests --source python --confirm
