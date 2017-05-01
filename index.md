PyCroscopy
==========

>_They don't think we're microscopists... Let's become pycroscopists then!_ 

>S.J to N.L, 2016

0. What?
--------------------
A suite of utilities for image processing and scientific analysis of imaging modalities such as multi-frequency scanning probe microscopy, scanning tunneling spectroscopy, x-ray diffraction microscopy, and transmission electron microscopy.
Classes implemented here are ported to a high performance computing platform at Oak Ridge National Laboratory ([ORNL](https://www.ornl.gov/)).

1. Why?
---------------
There is that little thing called _open science_... 

2. Who?
-----------
This project begun largely as an effort by materials scientists (_and a physicist_) at the **C**enter for **N**anophase **M**aterials **S**ciences ([CNMS](https://www.ornl.gov/facility/cnms)) to implement a python library that can withstand the I/O, processing, and analysis of the gargantuan stream of images that their microscopes generate (thanks to the large CNMS users community!).

By sharing our methodology and code for analyzing materials imaging we hope that it will benefit the wider community of materials science/physics. We also hope, quite ardently, that other materials scientists would follow suit. 
![](https://raw.githubusercontent.com/pycroscopy/pycroscopy/gh-pages/images/smiley_wink.png)

3. The Structure
-----------------
The package structure is simple, with 4 main modules:
   1. `io`: Input/Output from custom & proprietary microscope formats to HDF5.
   2. `processing`: Multivariate Statistics, Machine Learning, and Filtering.
   3. `analysis`: Model-dependent analysis of image information.
   4. `viz`: Visualization and interactive slicing of high-dimensional data by lightweight Qt viewers.

Once a user converts their microscope's data format into an HDF5 format, by simply extending some of the classes in `io`, the user gains access to the rest of the utilities present in `pycroscopy.*`.   
  
(On a High Performance Computing Platform if she/he is a CNMS user!   
  Sign up [here](https://www.ornl.gov/facility/cnms/subpage/user-program-overview)!) 

**_The PyCroscopy Team_**

@nlaanait (Numan Laanait), @ssomnath (Suhas Somnath), @CompPhysChris (Chris R. Smith), @stephenjesse (Stephen Jesse) and many more...

Acknoledgements
---------------
The PyCroscopy Team would like to thanks the developers of the following software packages:
   [Python](https://www.python.org)
   [Anaconda Python](https://www.continuum.io/anaconda-overview)
   [jupyter](http://jupyter.org/)
   [Spyder](https://pythonhosted.org/spyder/)
   [PyCharm](https://www.jetbrains.com/pycharm/)
   [GitKraken](https://www.gitkraken.com/)
   [GitHub Desktop](https://desktop.github.com/)
   [PyVmMonitor](http://www.pyvmmonitor.com/)
