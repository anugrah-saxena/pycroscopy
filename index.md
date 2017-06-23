What?
--------------------
A suite of utilities for image processing and scientific analysis of imaging modalities such as multi-frequency scanning probe microscopy, scanning tunneling spectroscopy, x-ray diffraction microscopy, and transmission electron microscopy.
Classes implemented here are ported to a high performance computing platform at Oak Ridge National Laboratory ([ORNL](https://www.ornl.gov/)).

More information on pycroscopy is available at our [project page](https://github.com/pycroscopy/pycroscopy)

Who?
-----------
This project begun largely as an effort by scientists and engineers at the **C**enter for **N**anophase **M**aterials **S**ciences ([CNMS](https://www.ornl.gov/facility/cnms)) to implement a python library that can support the I/O, processing, and analysis of the gargantuan stream of images that their microscopes generate (thanks to the large CNMS users community!).

By sharing our methodology and code for analyzing materials imaging we hope that it will benefit the wider community of materials science/physics. We also hope, quite ardently, that other materials scientists would follow suit. 
![](https://raw.githubusercontent.com/pycroscopy/pycroscopy/gh-pages/images/smiley_wink.png)

**_The (core) pycroscopy team_:**

@nlaanait (Numan Laanait), @ssomnath (Suhas Somnath), @CompPhysChris (Chris R. Smith), @stephenjesse (Stephen Jesse) and many more...

Why?
---------------
There is that little thing called _open science_... 

As we see it, there are a few ~~problems~~ oppurtunities in microscopy / imaging and materials science:

**1. Growing data sizes**
  * Cannot use desktop computers for analysis 
  * _Need: High performance computing, storage resources and compatible, scalable file structures_ 
  
**2. Increasing data complexity**
  * Sophisticated imaging and spectroscopy modes resulting in 5,6,7... dimensional data
  * _Need: Robust software and generalized data formatting_
  
**3. Multiple file formats**
  * Different formats from each instrument. Proprietary in most cases
  * Incompatible for correlation
  * _Need: Open, instrument independent data format_
  
**4. Disjoint communities** 
  * Similar analysis routines written by each community (SPM, STEM, TOF SIMs, XRD...) _independently_!
  * _Need: Centralized repository, instrument agonistic analysis routines that bring communities together_
  
**5. Expensive analysis software**
  * Software supplied with instruments often insufficient / incapable of custom analysis routines
  * Commercial software (Eg: Matlab, Origin..) are often prohibitively expensive.
  * _Need: Free, powerful, open souce, user-friendly software_

How?
-----------------
* pycroscopy uses an **instrument agnostic data structure** that facilitates the storage of data, regardless of dimensionality (conventional 2D images to 9D multispectral SPM datasets) or instrument of origin (AFMs, STMs, STEMs, TOF SIMS, and many more). This general defenition of data allows us to write a single and generalized version of analysis and processing functions that can be applied to any kind of data.  
* The data is stored in **[heirarchical data format (HDF5)](http://extremecomputingtraining.anl.gov/files/2015/03/HDF5-Intro-aug7-130.pdf)** files which:
   * Allow easy and open acceess to data from any programming language.
   * Accomodate datasets ranging from kilobytes (kB) to petabytes (pB)
   * Are readily compaible with supercomputers and support parallel I/O
   * Allows storage of relevant parameters along with data for improved traceability and reproducability of analysis
* Scientific workflows are developed and disseminated through **[jupyter notebooks](http://jupyter.org/)** that are interactive and portable web applications containing, text, images, code / scripts, and text-based and graphical results
* Once a user converts their microscope's data format into a HDF5 format, by simply extending some of the classes in `io`, the user gains access to the rest of the utilities present in `pycroscopy.*`. 
   * (On a High Performance Computing Platform if she/he is a CNMS user!   Sign up [here](https://www.ornl.gov/facility/cnms/subpage/user-program-overview)!) 
  
Acknowledgements
----------------
Besides the packages used in pycroscopy, we would like to thank the developers of the following software packages:
+ [Python](https://www.python.org)  
+ [Anaconda Python](https://www.continuum.io/anaconda-overview) 
+ [jupyter](http://jupyter.org/)
+ [PyCharm](https://www.jetbrains.com/pycharm/)
+ [GitKraken](https://www.gitkraken.com/)
