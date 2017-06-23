pycroscopy
==========

1. What?
--------------------
A suite of utilities for image processing and scientific analysis of imaging modalities such as multi-frequency scanning probe microscopy, scanning tunneling spectroscopy, x-ray diffraction microscopy, and transmission electron microscopy.
Classes implemented here are ported to a high performance computing platform at Oak Ridge National Laboratory ([ORNL](https://www.ornl.gov/)).

More information on pycroscopy available [here](https://github.com/pycroscopy/pycroscopy)

2. Why?
---------------
There is that little thing called _open science_... 

3. Who?
-----------
This project begun largely as an effort by scientists and engineers at the **C**enter for **N**anophase **M**aterials **S**ciences ([CNMS](https://www.ornl.gov/facility/cnms)) to implement a python library that can support the I/O, processing, and analysis of the gargantuan stream of images that their microscopes generate (thanks to the large CNMS users community!).

By sharing our methodology and code for analyzing materials imaging we hope that it will benefit the wider community of materials science/physics. We also hope, quite ardently, that other materials scientists would follow suit. 
![](https://raw.githubusercontent.com/pycroscopy/pycroscopy/gh-pages/images/smiley_wink.png)

**_The (core) pycroscopy team_**

@nlaanait (Numan Laanait), @ssomnath (Suhas Somnath), @CompPhysChris (Chris R. Smith), @stephenjesse (Stephen Jesse) and many more...

3. How?
-----------------
The package structure is simple, with 3 main modules:
   1. `io`: Input/Output from custom & proprietary microscope formats to HDF5.
   2. `processing`: Multivariate Statistics, Machine Learning, and Filtering.
   3. `analysis`: Model-dependent analysis of image information.

Once a user converts their microscope's data format into a HDF5 format, by simply extending some of the classes in `io`, the user gains access to the rest of the utilities present in `pycroscopy.*`. 
  
(On a High Performance Computing Platform if she/he is a CNMS user!   
  Sign up [here](https://www.ornl.gov/facility/cnms/subpage/user-program-overview)!) 
  
Scientific workflows are developed and disseminated through interactive [jupyter notebooks](http://jupyter.org/). 

Acknowledgements
----------------
Besides the packages used in pycroscopy, we would like to thank the developers of the following software packages:

   [Python](https://www.python.org)
   
   [Anaconda Python](https://www.continuum.io/anaconda-overview)
   
   [jupyter](http://jupyter.org/)
   
   [PyCharm](https://www.jetbrains.com/pycharm/)
   
   [GitKraken](https://www.gitkraken.com/)
