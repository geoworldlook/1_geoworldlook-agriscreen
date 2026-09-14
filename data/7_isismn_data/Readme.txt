IMPORTANT INFORMATION
If you use the ISMN data, please ensure that you correctly cite and acknowledge the ISMN and the contributing networks.
Check ismn_reference.bibtex for a list of ISMN and contributing network publications and ismn_acknowledgement.txt for
acknowledgement notes for contributing networks without publications.

Variables stored in separate files (Header+values)

Filename

	Data_separate_files_header_startdate(YYYYMMDD)_enddate(YYYYMMDD)_userid_randomstring_currrentdate(YYYYMMDD).zip
	
	e.g., Data_separate_files_header_20050316_20050601.zip

	
Folder structure

	Networkname
		Stationname

		
Dataset Filename

	CSE_Network_Station_Variablename_depthfrom_depthto_sensorname_redundancy_replacement_startdate_enddate.ext

	CSE	- Continental Scale Experiment (CSE) acronym, if not applicable use Networkname
	Network	- Network abbreviation (e.g., OZNET)
	Station	- Station name (e.g., Widgiewa)
	Variablename - Name of the variable in the file (e.g., Soil-Moisture)
	depthfrom - Depth in the ground in which the variable was observed (upper boundary)
	depthto	- Depth in the ground in which the variable was observed (lower boundary)
	Sensor name	- Name of the sensor used
    Redundancy Number - Indicates when multiple sensors are installed at the same depth and location
    Replacement Number - Indicates when a sensor has been exchanged at the very same position, e.g. due to malfunction
	startdate -	Date of the first dataset in the file (format YYYYMMDD)
	enddate	- Date of the last dataset in the file (format YYYYMMDD)
	ext	- Extension .stm (Soil Temperature and Soil Moisture Data Set see CEOP standard)
	
	e.g., OZNET_OZNET_Widgiewa_Soil-Temperature_0.150000_0.150000_CS616_1_2_20010103_20090812.stm

	
File Content Sample
	
	REMEDHUS   REMEDHUS        Zamarron          41.24100    -5.54300  855.00    0.05    0.05  (Header)
	2005/03/16 00:00    10.30 U	M	(Records)
	2005/03/16 01:00     9.80 U M

	
Header

	CSE Identifier - Continental Scale Experiment (CSE) acronym, if not applicable use Networkname
	Network	- Network abbreviation (e.g., OZNET)
	Station	- Station name (e.g., Widgiewa)
	Latitude - Decimal degrees. South is negative.
	Longitude - Decimal degrees. West is negative.
	Elevation - Meters above sea level
	Depth from - Depth in the ground in which the variable was observed (upper boundary)
	Depth to - Depth in the ground in which the variable was observed (lower boundary)

	
Record

	UTC Actual Date and Time
	yyyy/mm/dd HH:MM
	Variable Value
	ISMN Quality Flag
	Data Provider Quality Flag, if existing


Network Information

	AMMA-CATCH
		Abstract: This network consists of three supersites in Benin, Niger and Mali. Mali works operational since 2005, Niger and Benin since 2006. Several measurements in Mali and Niger are taken at the same station with the same sensor type in the same depth. They are located at the bottom (sensor CS616_1), middle (CS616_2) or top (CS616_3) of dune slopes (Mali) or from a plateau to the valley bottom (Niger).
		Continent: Africa
		Country: Benin, Niger, Mali
		Stations: 7
		Status: running
		Data Range: from 2005-01-01 
		Type: project
		Url: http://www.amma-catch.org
		Variables: soil moisture, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.10 - 0.10 m, 0.10 - 0.40 m, 0.20 - 0.20 m, 0.40 - 0.40 m, 0.40 - 0.70 m, 0.60 - 0.60 m, 0.70 - 1.00 m, 1.00 - 1.00 m, 1.00 - 1.30 m, 1.05 - 1.35 m, 1.20 - 1.20 m
		Soil Moisture Sensors: Campbell-CS616, 

	ARM
		Abstract: The soil moisture datasets collected at ARM facilities originates from two different instruments. SWATS instrument measure soil moisture in two different profiles at 8 depths from 0,05 to 1,75m, the SEBS instrument measure three profiles in depth of 0,025m. The site is managed by U.S. Department of Energy as part of the Atmospheric Radiation Measurement Climate Research Facility.
		Continent: Americas
		Country: USA
		Stations: 36
		Status: running
		Data Range: from 1996-02-05 
		Type: project
		Url: http://www.arm.gov/
		Variables: air temperature, precipitation, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.02 - 0.02 m, 0.05 - 0.05 m, 0.10 - 0.10 m, 0.15 - 0.15 m, 0.20 - 0.20 m, 0.25 - 0.25 m, 0.35 - 0.35 m, 0.50 - 0.50 m, 0.60 - 0.60 m, 0.75 - 0.75 m, 0.80 - 0.80 m, 0.85 - 0.85 m, 1.00 - 1.00 m, 1.25 - 1.25 m, 1.75 - 1.75 m
		Soil Moisture Sensors: Campbell-229, SMP1, Stevens-Hydraprobe-Digital, 

	BDF_Saxony
		Abstract: Intensive observation plots of the Permant Soil Monitoring Network in Saxony. All plots are located on agriculturally managed land.
		Continent: Europe
		Country: Germany
		Stations: 4
		Status: running
		Data Range: from 1993-01-01 
		Type: Project
		Url: https://www.boden.sachsen.de/bodenmonitoring-17257.html
		Variables: precipitation, soil moisture, 
		Soil Moisture Depths: 0.40 - 0.40 m, 0.45 - 0.45 m, 0.55 - 0.55 m, 0.65 - 0.65 m, 0.80 - 0.80 m, 1.00 - 1.00 m, 1.10 - 1.10 m, 1.40 - 1.40 m, 1.45 - 1.45 m, 1.50 - 1.50 m, 1.65 - 1.65 m
		Soil Moisture Sensors: DeltaT-ThetaProbe-ML2x, DeltaT-ThetaProbe-ML3, Imko-TrimeP2, Sentek-DaD, 

	Berlin
		Abstract: 
		Continent: Europe
		Country: Germany
		Stations: 23
		Status: running
		Data Range: from 2022-12-01 
		Type: campaign
		Url: 
		Variables: soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.15 - 0.15 m, 0.25 - 0.25 m, 0.35 - 0.35 m, 0.45 - 0.45 m, 0.55 - 0.55 m, 0.65 - 0.65 m, 0.75 - 0.75 m, 0.85 - 0.85 m
		Soil Moisture Sensors: Sentek-DaD, 

	BFG_Nw
		Abstract: 
		Continent: Europe
		Country: Germany
		Stations: 1
		Status: running
		Data Range: from 1986-11-01 
		Type: project
		Url: 
		Variables: air temperature, precipitation, soil moisture, soil temperature, surface temperature, 
		Soil Moisture Depths: 0.25 - 0.25 m, 0.50 - 0.66 m, 0.85 - 0.85 m, 1.05 - 1.05 m
		Soil Moisture Sensors: Imko-TrimeP2, Truebner-SMT100, 

	BIEBRZA_S-1
		Abstract: Preparation of the method for determining biomass and soil moisture changes on the basis of data delivered by recent satellite missions
		Continent: Europe
		Country: Poland
		Stations: 30
		Status: running
		Data Range: from 2015-09-15 
		Type: project
		Url: http://www.igik.edu.pl/en
		Variables: air temperature, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.10 - 0.10 m, 0.20 - 0.20 m, 0.50 - 0.50 m
		Soil Moisture Sensors: Meter-GS3, 

	COSMOS
		Abstract: A new project to measure soil moisture using a cosmic-ray technique. Currently, there are 67 stations deployed in 7 countries, which 59 are in USA, 1 in Germany, 1 in Switzerland, 1 in France, 1 in Brasil, 2 in Kenya, 1 in United Kingdom and 1 in Mexico.
		Continent: Americas
		Country: USA
		Stations: 109
		Status: running
		Data Range: from 2008-04-28 
		Type: project
		Url: http://cosmos.hwr.arizona.edu/
		Variables: soil moisture, 
		Soil Moisture Depths: 0.00 - 0.04 m, 0.00 - 0.05 m, 0.00 - 0.06 m, 0.00 - 0.07 m, 0.00 - 0.08 m, 0.00 - 0.09 m, 0.00 - 0.10 m, 0.00 - 0.11 m, 0.00 - 0.12 m, 0.00 - 0.13 m, 0.00 - 0.14 m, 0.00 - 0.15 m, 0.00 - 0.16 m, 0.00 - 0.17 m, 0.00 - 0.18 m, 0.00 - 0.19 m, 0.00 - 0.20 m, 0.00 - 0.21 m, 0.00 - 0.22 m, 0.00 - 0.23 m, 0.00 - 0.24 m, 0.00 - 0.25 m, 0.00 - 0.26 m, 0.00 - 0.27 m, 0.00 - 0.28 m, 0.00 - 0.29 m, 0.00 - 0.30 m, 0.00 - 0.31 m, 0.00 - 0.32 m, 0.00 - 0.33 m, 0.00 - 0.34 m, 0.00 - 0.36 m, 0.00 - 0.37 m, 0.00 - 0.38 m, 0.00 - 0.39 m, 0.00 - 0.40 m, 0.00 - 0.41 m, 0.00 - 0.44 m, 0.00 - 0.55 m, 0.00 - 0.69 m, 0.00 - 0.90 m
		Soil Moisture Sensors: Hydroinnova-CRS-1000B, 

	COSMOS-UK
		Abstract: The COSMOS-UK network is established and operated by the UK Centre for Ecology and Hydrology (UKCEH). It is the first network to systematically measure soil moisture throughout the UK, and represents a range of climate, soils and vegetation. The network consists of ~50 sites, each recording a number of hydrometeorological and soil variables. Each site hosts a cosmic-ray neutron sensor (CRNS); a novel sensor technology which counts fast neutrons in the surrounding atmosphere. In combination with the recorded hydrometeorological data, neutron counts are used to derive Volumetric Water Content (VWC) over a field scale (~0.1 km2) (COSMOS VWC), at daily resolution. Alongside the CRNS, each site hosts several point soil moisture probes recording at 30 minute resolution. More information is available from the COSMOS-UK website: https://cosmos.ceh.ac.uk/ . The full dataset, along with quality flags, is available at: https://doi.org/10.5285/5060cc27-0b5b-471b-86eb-71f96da0c80f .


************************************************************************************************************
IMPORTANT NOTE: The Cosmic-ray neutron sensor (CRNS) is placed just above the ground and counts the naturally occurring neutrons (originating from cosmic rays). The neutrons are scattered by hydrogen atoms, which are present primarily in the soil water. The CRNS neutron count rate (after corrections) reduces with increasing soil moisture content, and can therefore be used, via a calibration curve, to infer the soil Volumetric Water Content (VWC). The CRNS counts neutrons which may have been scattered many times, such that they may have interacted with the ground soil moisture over distances of more than 200 m from the probe, and from tens centimetres of soil depth. This local scattering of neutrons determines the horizontal and vertical footprint of the sensor, or the measurement support volume, and yields the important characteristic of averaging the soil moisture measurement over a large area. Using neutron scattering models, the typical footprint is determined (~12 hectares), although there is some dependence on the VWC, particularly for the soil depth of measurement. For this reason, the CRNS depth of measurement is given as an average for the time series and location, but it should be appreciated that actual sensing depth will be reduced in wet conditions, compared with dry conditions (from around 10 cm to 30 cm depth respectively).
************************************************************************************************************

		Continent: Europe
		Country: UK
		Stations: 49
		Status: running
		Data Range: from 2013-10-01 
		Type: project
		Url: https://cosmos.ceh.ac.uk/
		Variables: air temperature, precipitation, snow depth, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.00 - 0.30 m, 0.05 - 0.05 m, 0.10 - 0.10 m, 0.15 - 0.15 m, 0.25 - 0.25 m, 0.50 - 0.50 m
		Soil Moisture Sensors: Acclima-TDT, Hydroinnova-CRS-1000B, 

	CTP_SMTMN
		Abstract: A dense monitoring network that consists of 56 stations is established on the central Tibetan Plateau to measure two state variables (soil moisture and temperature) at three spatial scales (1.0, 0.3, 0.1 degree) and four soil depths (0~5, 10, 20, and 40 cm). Elevations of these stations vary over 4470~4950 m. The experimental area is characterized by low biomass, high soil moisture dynamic range, and typical freeze-thaw cycle. As auxiliary parameters of this network, soil texture and soil organic carbon content are measured at each station to support further studies. All the sensors have been calibrated by taking account of the impact of soil texture and soil organic carbon content on the measurements. 
As the highest soil moisture network above sea level in the world, this network meets the requirement for evaluating a variety of soil moisture products and for soil moisture scaling analyses. 
Note that, 
a)	some of the stations are shared by two or three sub-scale networks (indicated by the station names) and thus the number of station names is up to 69 in total; 
b)	in order to ensure the continuous measurements of the near surface (0~5 cm) SM/TM, the original surface layer sensor (when get damaged) is usually replaced with another sensor at deeper depth during field maintenance. Therefore there may be offset in a time series before and after the replacing time point (shown in Table 1). 
Table 1. Sensor replacing/exchanging time points at specific stations. 
Station_Name	0-0.05 m	0.40 m
M19	        10/13/2012	
L01	          6/14/2012	  6/14/2012
L07_M13	  6/15/2012	  6/15/2012
L35	        10/15/2012	10/15/2012
M03	        10/13/2012	10/13/2012
M07_S01	10/13/2012	10/13/2012

		Continent: Asia
		Country: China
		Stations: 57
		Status: running
		Data Range: from 2007-07-01 
		Type: project
		Url: http://dam.itpcas.ac.cn/rs/?q=data#CTP-SMTMN
		Variables: soil moisture, soil temperature, 
		Soil Moisture Depths: 0.00 - 0.05 m, 0.10 - 0.10 m, 0.20 - 0.20 m, 0.40 - 0.40 m
		Soil Moisture Sensors: Meter-5TM, 

	CW3E
		Abstract: Research lab
		Continent: Americas
		Country: USA
		Stations: 24
		Status: running
		Data Range: from 2004-08-01 
		Type: Hydroclimate research
		Url: https://cw3e.ucsd.edu/
		Variables: air temperature, precipitation, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.05 - 0.05 m, 0.10 - 0.10 m, 0.10 - 0.10 m, 0.15 - 0.15 m, 0.15 - 0.15 m, 0.20 - 0.20 m, 0.20 - 0.20 m, 0.50 - 0.50 m, 0.51 - 0.51 m, 1.00 - 1.00 m, 1.02 - 1.02 m
		Soil Moisture Sensors: Campbell-CS616, Stevens-Hydraprobe-Digital, 

	DAHRA
		Abstract: Earth Observation of long term changes in land surface moisture conditions
		Continent: Africa
		Country: Senegal
		Stations: 1
		Status: running
		Data Range: from 2002-07-04 
		Type: project
		Url: https://ign.ku.dk/english/research/geography/environment-society-developing-countries/
		Variables: air temperature, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.10 - 0.10 m, 0.30 - 0.30 m, 0.50 - 0.50 m, 1.00 - 1.00 m
		Soil Moisture Sensors: DeltaT-ThetaProbe-ML3, 

	DWD
		Abstract: The soil-physical boundary conditions of the soil moisture probes used were determined for the individual sites during installation by means of simple soil sampling and finger tests on the basis of the Soil Science Mapping Guide (KA 5). At present, however, calibration sampling is still being carried out at the sites and, in the future, site-specific soil physics laboratory tests are also planned. The measured values should therefore be regarded and used as preliminary raw data, particularly with regard to the absolute level.


************************************************************************************************************
Die bodenphysikalischen Randbedingungen der eingesetzten Bodenfeuchtesonden sind für die einzelnen Standorte beim Einbau durch einfache Bodenansprachen und Fingerproben auf der Basis der Bodenkundlichen Kartieranleitung (KA 5) festgelegt worden. Derzeit werden an den Standorten aber noch Kalibrierbeprobungen vorgenommen und perspektivisch sind auch standörtliche bodenphysikalische Laboruntersuchungen geplant. Die Messwerte sollten deshalb insbesondere bezüglich des absoluten Niveaus als vorläufige Rohdaten betrachtet und verwendet werden.
		Continent: Europe
		Country: Germany
		Stations: 20
		Status: operational
		Data Range: from 2024-01-01 
		Type: continous measuring network
		Url: 
		Variables: precipitation, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.15 - 0.15 m, 0.25 - 0.25 m, 0.35 - 0.35 m, 0.45 - 0.45 m, 0.55 - 0.55 m, 0.65 - 0.65 m, 0.75 - 0.75 m, 0.85 - 0.85 m
		Soil Moisture Sensors: Sentek-DaD, 

	FLUXNET-AMERIFLUX
		Abstract: Datasets of 2 stations near the city of Sacramento are provided. They are managed by Dennis D. Baldocchi, University of California, Berkeley. 
		Continent: Americas
		Country: USA
		Stations: 8
		Status: running
		Data Range: from 2000-10-22 
		Type: project
		Url: http://ameriflux.lbl.gov/
		Variables: air temperature, precipitation, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.00 - 0.00 m, 0.00 - 0.15 m, 0.02 - 0.02 m, 0.05 - 0.05 m, 0.10 - 0.10 m, 0.15 - 0.30 m, 0.20 - 0.20 m, 0.30 - 0.45 m, 0.45 - 0.60 m, 0.50 - 0.50 m
		Soil Moisture Sensors: Campbell-CS655, DeltaT-ThetaProbe-ML2x, DeltaT-ThetaProbe-ML3, ES-Moisture-Point, 

	FMI
		Abstract: The finnish network "FMI" includes one station that contains multiple soil moisture measurements in 2cm and 10cm depth, taken only a few meters next to each other. Additionaly air temperature is measured in 2m height and soil temperature in 2cm depth. The datasets start at 2007-01-25 and are updated once a day. The FMI is the first network that has been implemented with data updates in Near Real Time.
		Continent: Europe
		Country: Finland
		Stations: 27
		Status: running
		Data Range: from 2007-01-25 
		Type: project
		Url: http://fmiarc.fmi.fi/
		Variables: air temperature, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.02 - 0.02 m, 0.05 - 0.05 m, 0.10 - 0.10 m, 0.20 - 0.20 m, 0.40 - 0.40 m, 0.60 - 0.60 m, 0.80 - 0.80 m
		Soil Moisture Sensors: Campbell-CS655, DeltaT-ThetaProbe-ML3, Meter-5TE, 

	FR_Aqui
		Abstract: The Fr_Aqui network is located in France and hosted by the Institue of Agricultural Research (INRA); it consists of 5 stations with soil moisture and soil temperature measurements in 6 different  depths.
		Continent: Europe
		Country: France
		Stations: 5
		Status: running
		Data Range: from 2010-01-01 
		Type: meteo
		Url: 
		Variables: soil moisture, soil temperature, 
		Soil Moisture Depths: 0.01 - 0.01 m, 0.03 - 0.03 m, 0.05 - 0.05 m, 0.10 - 0.10 m, 0.15 - 0.15 m, 0.20 - 0.20 m, 0.21 - 0.21 m, 0.25 - 0.25 m, 0.30 - 0.30 m, 0.34 - 0.34 m, 0.40 - 0.40 m, 0.45 - 0.45 m, 0.50 - 0.50 m, 0.55 - 0.55 m, 0.56 - 0.56 m, 0.70 - 0.70 m, 0.80 - 0.80 m, 0.90 - 0.90 m
		Soil Moisture Sensors: DeltaT-ThetaProbe-ML3, 

	GROW
		Abstract: The GROW Observatory (GROW) is a European-wide project engaging thousands of growers, scientists and others passionate about the land. We will discover together, using simple tools to better manage soil and grow food, while contributing to vital scientific environmental monitoring.
		Continent: Europe
		Country: UK
		Stations: 151
		Status: inactive
		Data Range: from 2016-11-01  to 2019-10-31
		Type: project
		Url: https://growobservatory.org/index.html
		Variables: air temperature, soil moisture, 
		Soil Moisture Depths: 0.00 - 0.10 m
		Soil Moisture Sensors: Parrot-flower-power, 

	HOAL
		Abstract: 
		Continent: Europe
		Country: Austria
		Stations: 33
		Status: running
		Data Range: from 2013-12-07 
		Type: research network

		Url: https://hoal.hydrology.at/research/soil-moisture

		Variables: soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.10 - 0.10 m, 0.20 - 0.20 m, 0.50 - 0.50 m, 1.00 - 1.00 m
		Soil Moisture Sensors: Sceme-Spade-TDT, 

	HOBE
		Abstract: Soil moisture and soil temperature network with 30 stations within the area of major signal contribution of one selected SMOS grid node in the Skjern River Catchment
		Continent: Europe
		Country: Denmark
		Stations: 32
		Status: inactive
		Data Range: from 2009-09-08  to 2019-03-13
		Type: project
		Url: http://www.hobe.dk/
		Variables: soil moisture, soil temperature, 
		Soil Moisture Depths: 0.00 - 0.05 m, 0.20 - 0.25 m, 0.50 - 0.55 m
		Soil Moisture Sensors: Meter-5TE, 

	HYDROL-NET_PERUGIA
		Abstract: This network has 1 station called WEEF (Water Engineering Experimental Field) near the city of Perugia, Central Italy. It provides of measurements of soil moisture at 4 different depths, soil temperature at 2 depths, precipitation, and air temperature. It is operated by the Department of Civil and Environmental Engineering of the University of Perugia since the beginning of 2010.
		Continent: Europe
		Country: Italy
		Stations: 2
		Status: running
		Data Range: from 2010-01-01 
		Type: project
		Url: http://www.ing1.unipg.it/
		Variables: air temperature, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.15 - 0.15 m, 0.25 - 0.25 m, 0.35 - 0.35 m
		Soil Moisture Sensors: Trase-BE, 

	IPE
		Abstract: 
		Continent: Europe
		Country: Spain
		Stations: 2
		Status: running
		Data Range: from 2008-04-03 
		Type: meteo
		Url: 
		Variables: air temperature, precipitation, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.00 - 0.06 m, 0.00 - 0.30 m, 0.10 - 0.10 m
		Soil Moisture Sensors: Campbell-CS616, Campbell-CS650, DeltaT-ThetaProbe-ML3, 

	iRON
		Abstract: A 10-station network measuring soil moisture and other meteorological variables in a mountain environment.
		Continent: Americas
		Country: USA
		Stations: 7
		Status: running
		Data Range: from 2012-06-07 
		Type: meteo
		Url: https://agci.org/iron
		Variables: air temperature, precipitation, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.20 - 0.20 m, 0.50 - 0.50 m
		Soil Moisture Sensors: Meter-10HS, Meter-EC5, 

	KIHS_CMC
		Abstract: 
		Continent: Asia
		Country: Korea
		Stations: 18
		Status: running
		Data Range: from 2019-03-20 
		Type: project
		Url: http://kihs.re.kr
		Variables: soil moisture, 
		Soil Moisture Depths: 0.10 - 0.10 m, 0.30 - 0.30 m, 0.40 - 0.40 m, 0.50 - 0.50 m, 0.60 - 0.60 m, 0.90 - 0.90 m
		Soil Moisture Sensors: SE-TDR, 

	KIHS_SMC
		Abstract: 
		Continent: Asia
		Country: Korea
		Stations: 19
		Status: running
		Data Range: from 2019-03-21 
		Type: campaign
		Url: http://kihs.re.kr
		Variables: soil moisture, 
		Soil Moisture Depths: 0.10 - 0.10 m, 0.20 - 0.20 m, 0.30 - 0.30 m, 0.40 - 0.40 m, 0.50 - 0.50 m, 0.60 - 0.60 m
		Soil Moisture Sensors: SE-TDR, 

	LABFLUX
		Abstract: The Lab performs research, tutorial ad dissemination regarding measurements and modeling of water and moisture fluxes in the natural, agricultural and built environments. Main focus is on porous media like soil, snow and wood. Specifically addressed are the monitoring of : meteorological variables, energy fluxes, soil-plant-atmosphere interactions, water dynamics, and hillslope processes.
		Continent: Europe
		Country: Italy
		Stations: 4
		Status: running
		Data Range: from 2012-01-01 
		Type: project
		Url: https://www.dist.polito.it/il_dipartimento/laboratori/labflux
		Variables: air temperature, precipitation, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.10 - 0.10 m, 0.20 - 0.20 m, 0.40 - 0.40 m
		Soil Moisture Sensors: Campbell-CS616, Meter-EC5, 

	LAB-net
		Abstract: In Chile, remote sensing applications related to soil moisture and evapotranspiration estimates have increased during the last decades because of the drought and the water use conflicts which generate a strong interest on water demand. To address these problems on water balance in large scales by using remote sensing imagery, LAB-net was created as the first soil moisture network located in Chile over four different land cover types. These land cover types are vineyard and olive orchards located in a semi-arid region of Copiapó Valley, a well irrigated raspberry crop located in the central zone of of Tinguiririca Valley and a green grass rangeland located Austral zone of Chile. Over each site, a well implemented meteorological station is continuously measuring a 5 minute intervals above the following parameters: soil moisture and temperature at two ground levels (5 and 20 cm), air temperature and relative humidity, net radiation, global radiation, brightness surface temperature (8 – 14 µm), rainfall and ground fluxes. This is the first approach of an integrated soil moisture network in Chile. The data generated by this network is freely available for any research or scientific purpose related to current and future soil moisture satellite missions.    

		Continent: Americas
		Country: Chile
		Stations: 4
		Status: running
		Data Range: from 2014-07-18 
		Type: meteo
		Url: http://www.biosfera.uchile.cl/LAB-net.html

		Variables: air temperature, precipitation, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.07 - 0.07 m, 0.10 - 0.10 m, 0.20 - 0.20 m
		Soil Moisture Sensors: Campbell-CS616, Campbell-CS650, Campbell-CS655, 

	MAQU
		Abstract: The MAQU network consist of 20 stations located at the eastern edge of the Tibetan Plateau in Central China at an altitude of more than 3000 m .a.s.l. The stations are operated by University of Twente, Faculty of Geo-Information Science and  Earth Observation (ITC), and the Chinese Academy of Science - Cold and Arid Regions Environmental and Engineering Research Institute (CAS-CAREERI). The soil moisture datasets were kindly provided by Laura Dente and Bob Su from the ITC and J. Wen of the CAS.
		Continent: Asia
		Country: China
		Stations: 27
		Status: running
		Data Range: from 2008-07-01 
		Type: project
		Url: https://www.itc.nl/about-itc/organization/scientific-departments/water-resources/earth-observation-sites/tibetan-plateau-peoples-republic-of-china/
		Variables: soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.10 - 0.10 m, 0.20 - 0.20 m, 0.40 - 0.40 m, 0.80 - 0.80 m
		Soil Moisture Sensors: Meter-5TM, 

	MOL-RAO
		Abstract: This network is operated from the German Meteorological Service and consists of two stations. While the Station Falkenberg has a grass type vegetation, Kehrigk is situated in a pine forest. Volumetric soil moisture, soil temperature, air temperature and precipitation are provied for the period from 2003 to 2008. 
		Continent: Europe
		Country: Germany
		Stations: 2
		Status: running
		Data Range: from 2003-01-01 
		Type: project
		Url: http://www.dwd.de/mol
		Variables: air temperature, precipitation, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.08 - 0.08 m, 0.10 - 0.10 m, 0.15 - 0.15 m, 0.20 - 0.20 m, 0.30 - 0.30 m, 0.45 - 0.45 m, 0.60 - 0.60 m, 0.90 - 0.90 m, 1.50 - 1.50 m
		Soil Moisture Sensors: Imko-TrimeTDR, 

	NAQU
		Abstract: 
		Continent: Asia
		Country: China
		Stations: 11
		Status: running
		Data Range: from 2006-07-01 
		Type: campaign
		Url: https://www.itc.nl/about-itc/organization/scientific-departments/water-resources/earth-observation-sites/tibetan-plateau-peoples-republic-of-china/
		Variables: soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.10 - 0.10 m, 0.20 - 0.20 m, 0.40 - 0.40 m, 0.80 - 0.80 m
		Soil Moisture Sensors: Meter-5TM, 

	NGARI
		Abstract: 
		Continent: Asia
		Country: China
		Stations: 23
		Status: running
		Data Range: from 2010-07-01 
		Type: campaign
		Url: https://www.itc.nl/about-itc/organization/scientific-departments/water-resources/earth-observation-sites/tibetan-plateau-peoples-republic-of-china/
		Variables: soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.10 - 0.10 m, 0.20 - 0.20 m, 0.40 - 0.40 m, 0.80 - 0.80 m
		Soil Moisture Sensors: Meter-5TM, 

	NVE
		Abstract: Ground water and soil moisture network

		Continent: Europe
		Country: Norway
		Stations: 8
		Status: running
		Data Range: from 1989-06-15 
		Type: permanent

		Url: https://www.nve.no/hydrology/?ref=mainmenu
		Variables: air temperature, precipitation, snow depth, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.10 - 0.10 m, 0.20 - 0.20 m, 0.30 - 0.30 m, 0.40 - 0.40 m, 0.50 - 0.50 m, 0.60 - 0.60 m, 1.00 - 1.00 m
		Soil Moisture Sensors: DeltaT-PR1-daily-averages, DeltaT-PR2, DeltaT-PR2-daily-averages, Meter-5TM-daily-averages, 

	OZNET
		Abstract: 
		Continent: Oceania
		Country: Australia
		Stations: 38
		Status: running
		Data Range: from 2001-01-01 
		Type: project
		Url: http://www.oznet.org.au/
		Variables: soil moisture, soil suction, soil temperature, 
		Soil Moisture Depths: 0.00 - 0.05 m, 0.00 - 0.08 m, 0.00 - 0.30 m, 0.15 - 0.25 m, 0.30 - 0.60 m, 0.57 - 0.87 m, 0.60 - 0.90 m
		Soil Moisture Sensors: Campbell-CS615, Campbell-CS616, Sentek-EnviroSCAN, Stevens-Hydraprobe-Digital, 

	PBO_H2O
		Abstract: The soil moisture data is measured using GPS reflections.
		Continent: Americas
		Country: USA
		Stations: 163
		Status: inactive
		Data Range: from 2007-01-01 
		Type: project
		Url: https://gnss-reflections.org/maps?product=smc
		Variables: air temperature, precipitation, snow depth, soil moisture, 
		Soil Moisture Depths: 0.00 - 0.05 m
		Soil Moisture Sensors: GPS, 

	PTSMN
		Abstract: 
		Continent: Oceania
		Country: New Zealand
		Stations: 20
		Status: running
		Data Range: from 2016-11-01 
		Type: project
		Url: 
		Variables: soil moisture, 
		Soil Moisture Depths: 0.07 - 0.13 m, 0.17 - 0.23 m, 0.27 - 0.33 m, 0.37 - 0.43 m
		Soil Moisture Sensors: AquaCheck-CP, 

	REMEDHUS
		Abstract: 
		Continent: Europe
		Country: Spain
		Stations: 24
		Status: running
		Data Range: from 2005-01-01 
		Type: project
		Url: http://campus.usal.es/~hidrus/
		Variables: soil moisture, soil temperature, 
		Soil Moisture Depths: 0.00 - 0.05 m
		Soil Moisture Sensors: Stevens-Hydraprobe-Digital, 

	RISMA
		Abstract: In 2010 and 2011, Agriculture and Agri-Food Canada (AAFC), with the collaboration of Environment Canada, established three in situ monitoring networks near Kenaston (Saskatchewan), Carman (Manitoba) and Casselman (Ontario) as part of the Sustainable Agriculture Environmental Systems (SAGES) project titled Earth Observation Information on Crops and Soils for Agri-Environmental Monitoring in Canada.
		Continent: Americas
		Country: Canada
		Stations: 24
		Status: running
		Data Range: from 2013-06-15 
		Type: project
		Url: https://agriculture.canada.ca/en/agricultural-production/soil-and-land/real-time-situ-soil-monitoring-agriculture
		Variables: air temperature, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.00 - 0.05 m, 0.05 - 0.05 m, 0.20 - 0.20 m, 0.50 - 0.50 m, 1.00 - 1.00 m, 1.50 - 1.50 m
		Soil Moisture Sensors: Stevens-Hydraprobe-Digital, 

	ROMPS
		Abstract: The Regional Research Network „Water in Central Asia“ (CAWa) funded by the German Federal Foreign Office consists of 18 remotely operated multi-parameter stations (ROMPS) in Central Asia. These stations were installed by the German Research Centre for Geosciences (GFZ) in Potsdam, Germany in close cooperation with the Central-Asian Institute for Applied Geosciences (CAIAG) in Bishkek, Kyrgyzstan, the national hydrometeorological services in Uzbekistan and Tajikistan, the Ulugh Beg Astronomical Institute in Tashkent, Uzbekistan, and the Kabul Polytechnic University, Afghanistan.
		Continent: Asia
		Country: Kyrgyzstan, Tajikistan, Uzbekistan, Afghanistan
		Stations: 9
		Status: running
		Data Range: from 2010-01-01 
		Type: meteo
		Url: http://sdss.caiag.kg/sdss/index.php?&page=measure_page
		Variables: air temperature, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.10 - 0.10 m, 0.20 - 0.20 m, 0.40 - 0.40 m, 0.60 - 0.60 m, 0.80 - 0.80 m, 1.00 - 1.00 m
		Soil Moisture Sensors: Campbell-CS616, 

	RSMN
		Abstract: The project proposal aims at paving the way for the utilisation of satellite derived soil moisture products in Romania, creating the framework for the validation and evaluation of actual & future satellite microwave soil moisture derived products, demonstrating its value, and by developing the necessary expertise for successfuly approaching implementations in the Societal Benefit Areas (as they were defined in GEOSS)

		Continent: Europe
		Country: Romania
		Stations: 20
		Status: running
		Data Range: from 2014-04-09 
		Type: meteo
		Url: http://assimo.meteoromania.ro
		Variables: air temperature, precipitation, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.00 - 0.05 m
		Soil Moisture Sensors: Meter-5TM, 

	RU-ADDFerti
		Abstract: 
		Continent: Europe
		Country: Germany
		Stations: 30
		Status: running
		Data Range: from 2023-06-01 
		Type: project
		Url: 
		Variables: soil moisture, soil temperature, 
		Soil Moisture Depths: 0.25 - 0.25 m, 0.50 - 0.50 m
		Soil Moisture Sensors: Dragino-LSE01, 

	Ru_CFR
		Abstract: 
		Continent: Europe
		Country: Russia
		Stations: 2
		Status: running
		Data Range: from 2015-05-25 
		Type: fluxnet
		Url: 
		Variables: air temperature, precipitation, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.15 - 0.15 m, 0.50 - 0.50 m, 0.80 - 0.80 m, 1.00 - 1.00 m
		Soil Moisture Sensors: Stevens-Hydraprobe-Digital, 

	SCAN
		Abstract: Soil Climate Analysis Network contains 239 stations all over the USA including stations in Alaska, Hawaii, Puerto Rico or even one in Antarctica. Apart from soil moisture and soil temperature, also precipitation and air temperature are measured. Some stations have also additional measurements of snow depth and snow water equivalent. Almost 150 stations are updated on daily basis. The network is operated by the USDA NRCS National Water and Climate Center with assistance from the USDA NRCS National Soil Survey Center.
		Continent: Americas
		Country: USA
		Stations: 222
		Status: running
Data Range: 

		Type: project
		Url: http://www.wcc.nrcs.usda.gov/
		Variables: air temperature, precipitation, snow depth, snow water equivalent, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.10 - 0.10 m, 0.15 - 0.15 m, 0.20 - 0.20 m, 0.25 - 0.25 m, 0.30 - 0.30 m, 0.38 - 0.38 m, 0.51 - 0.51 m, 0.61 - 0.61 m, 0.69 - 0.69 m, 0.76 - 0.76 m, 0.84 - 0.84 m, 0.89 - 0.89 m, 1.02 - 1.02 m, 1.09 - 1.09 m, 1.30 - 1.30 m, 1.42 - 1.42 m
		Soil Moisture Sensors: not-specified, Stevens-Hydraprobe-Analog, Stevens-Hydraprobe-Digital, 

	SD_DEM
		Abstract: Meteorological data and soil data have been collected at a site in the central Sudan from 2002 to 2012. The site is a sparse savanna in the semiarid region of Sudan. In addition to basic meteorological variables, soil properties (temperature, water content, and heat flux) and radiation (global radiation, net radiation, and photosynthetic active radiation) were measured. The dataset has a temporal resolution of 30 minutes and provides general data for calibration and validation of ecosystem models and remote-sensing-based assessments, and it is relevant for studies of ecosystem properties and processes.
		Continent: Africa
		Country: Sudan
		Stations: 1
		Status: running
		Data Range: from 2002-02-08 
		Type: project
		Url: http://dx.doi.org/10.7167/2013/297973
		Variables: air temperature, precipitation, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.10 - 0.10 m, 0.15 - 0.15 m, 0.30 - 0.30 m, 0.60 - 0.60 m, 1.00 - 1.00 m, 1.50 - 1.50 m, 2.00 - 2.00 m
		Soil Moisture Sensors: Campbell-CS615, Campbell-CS616, Campbell-CS616-daily-averages, Campbell-CS650-daily-averages, Stevens-Hydraprobe-Analog, 

	SKKU
		Abstract: 
		Continent: Asia
		Country: Korea
		Stations: 15
		Status: running
Data Range: 

		Type: project
		Url: 
		Variables: soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.10 - 0.10 m, 0.20 - 0.20 m, 0.30 - 0.30 m, 0.40 - 0.40 m
		Soil Moisture Sensors: Meter-5TM, 

	SMN-SDR
		Abstract: The SMN-SDR was established during the Soil Moisture Experiment in the Luan River of China (SMELR, Zhao et al., 2020), from July 18, 2018 to September 28, 2018.
The coverage of entire network is about 10,000 km2 (115.5-116.5°E, 41.5-42.5°N). 
The topography of the SMN-SDR is relatively flat, and land surfaces are typically dominated by grasslands and croplands.
A total of 34 stations are set up in the network with three sampling scales including 100 km (large scale), 50 km (medium scale), and 10 km (small scale).
These were initially designed to match different scales of land surface modelling and various satellite products (SMAP, SMOS, AMSR2, and downscaled soil moisture products).
The soil moisture sensors used are Decagon 5TM with five measuring depths (3, 5, 10, 20, and 50 cm) installed for each station. 
Of the 34 station, there are 20 stations equipped with HOBO rain gauges.
Undisturbed soil samples at each layer of soil for each station was taken to analyze the gravimetric/volumetric water content, bulk density, and soil texture for a further specific calibration. 
The power supply is provided by solar panels and all data can be transmitted wirelessly to a server. 
The sampling interval of the data recording time is 10 (before June 2019) or 15 minutes (after June 2019).
This network can improve the comprehensive observation capabilities of key water cycle parameters in the ShanDian River basin and provide long-term ground reference data for satellite- and model-based soil moisture products.
		Continent: Asia
		Country: China
		Stations: 34
		Status: running
		Data Range: from 2018-07-18 
		Type: Soil moisture experiment in the Luan River
		Url: https://doi.org/10.11888/Soil.tpdc.271425

https://doi.org/10.11888/Soil.tpdc.271434
		Variables: soil moisture, soil temperature, 
		Soil Moisture Depths: 0.03 - 0.03 m, 0.05 - 0.05 m, 0.10 - 0.10 m, 0.20 - 0.20 m, 0.50 - 0.50 m
		Soil Moisture Sensors: Meter-5TM, 

	SMOSMANIA
		Abstract: 
		Continent: Europe
		Country: France
		Stations: 22
		Status: running
		Data Range: from 2003-01-01 
		Type: project
		Url: http://www.hymex.org
		Variables: soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.10 - 0.10 m, 0.20 - 0.20 m, 0.30 - 0.30 m
		Soil Moisture Sensors: DeltaT-ThetaProbe-ML2x, DeltaT-ThetaProbe-ML3, 

	SNOTEL
		Abstract: The Natural Resources Conservation Service (NRCS) installs, operates, and maintains an extensive, automated system to collect snowpack and related climatic data in the Western United States called SNOTEL (for SNOwpack TELemetry). The system evolved from NRCS"s Congressional mandate in the mid-1930"s "to measure snowpack in the mountains of the West and forecast the water supply." The programs began with manual measurements of snow courses; since 1980, SNOTEL has reliably and efficiently collected the data needed to produce water supply forecasts and to support the resource management activities of NRCS and others.
		Continent: Americas
		Country: USA
		Stations: 509
		Status: running
		Data Range: from 1980-01-01 
		Type: project
		Url: http://www.wcc.nrcs.usda.gov/
		Variables: air temperature, snow depth, snow water equivalent, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.00 - 0.00 m, 0.05 - 0.05 m, 0.10 - 0.10 m, 0.20 - 0.20 m, 0.30 - 0.30 m, 0.36 - 0.36 m, 0.40 - 0.40 m, 0.46 - 0.46 m, 0.51 - 0.51 m, 0.61 - 0.61 m, 0.69 - 0.69 m, 0.81 - 0.81 m, 0.99 - 0.99 m, 1.02 - 1.02 m, 2.03 - 2.03 m
		Soil Moisture Sensors: not-specified, Stevens-Hydraprobe-Analog, Stevens-Hydraprobe-Digital, 

	SOILSCAPE
		Abstract: 
		Continent: Americas
		Country: USA
		Stations: 224
		Status: running
Data Range: 

		Type: project
		Url: http://soilscape.usc.edu/
		Variables: air temperature, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.04 - 0.04 m, 0.05 - 0.05 m, 0.10 - 0.10 m, 0.13 - 0.13 m, 0.15 - 0.15 m, 0.17 - 0.17 m, 0.20 - 0.20 m, 0.23 - 0.23 m, 0.28 - 0.28 m, 0.29 - 0.29 m, 0.30 - 0.30 m, 0.32 - 0.32 m, 0.35 - 0.35 m, 0.36 - 0.36 m, 0.37 - 0.37 m, 0.38 - 0.38 m, 0.39 - 0.39 m, 0.40 - 0.40 m, 0.41 - 0.41 m, 0.42 - 0.42 m, 0.43 - 0.43 m, 0.45 - 0.45 m, 0.46 - 0.46 m, 0.47 - 0.47 m, 0.48 - 0.48 m, 0.50 - 0.50 m, 0.60 - 0.60 m, 0.70 - 0.70 m, 0.75 - 0.75 m, 0.90 - 0.90 m
		Soil Moisture Sensors: Meter-5TM, Meter-EC5, Meter-Teros12, 

	SONTE-China
		Abstract: An automatic soil observation network in typical ecosystems in China (SONTE-China) was established by the Aerospace Information Research Institute (AIR), Chinese Academy of Sciences (CAS), and National Engineering Research Center of Satellite Remote Sensing Applications(NECRSA), which were of the same unified sensor, unified sample design, unified acquisition depth, unified calibration method, unified data processing process. SONTE-China covers the main ecosystems (including grassland, farmland, desert and forest) and dry and wet climate zones in China. It can automatically obtain pixel scale soil temperature and soil moisture, which can not only serve the development and verification of high-resolution satellite remote sensing soil moisture products but also provide basic data for research in the fields of weather forecasting, flood forecasting, agricultural drought monitoring and water resources management.
		Continent: Asia
		Country: China
		Stations: 20
		Status: running
		Data Range: from 2019-01-01 
		Type: project
		Url: 
		Variables: soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.10 - 0.10 m, 0.20 - 0.20 m, 0.40 - 0.40 m
		Soil Moisture Sensors: Meter-5TM, 

	STEMS
		Abstract: Soil Moisture Network installed in rainfed vineyard plots, with different inter-rows soil management. The plots are also monitored for runoff and soil erosion. Weather data available from a station near the plots.
		Continent: Europe
		Country: Italy
		Stations: 11
		Status: running
		Data Range: from 2015-12-04 
		Type: campaign
		Url: https://sustag.to.cnr.it/index.php/cannona-db
		Variables: air temperature, precipitation, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.10 - 0.10 m, 0.20 - 0.20 m, 0.30 - 0.30 m, 0.40 - 0.40 m, 0.50 - 0.50 m
		Soil Moisture Sensors: Meter-5TM, Meter-EC5, Senseca-HD3910, 

	TAHMO
		Abstract: The Trans-African HydroMeteorological Observatory (TAHMO) aims to develop a vast network of weather stations across Africa. Current and historic weather data is important for agricultural, climate monitoring, and many hydro-meteorological applications.
		Continent: Africa
		Country: Côte d'Ivoire, Nigeria, Ghana, Uganda, Rwanda, Kenya
		Stations: 70
		Status: running
		Data Range: from 2015-06-17 
		Type: project
		Url: https://tahmo.org/
		Variables: air temperature, precipitation, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.10 - 0.10 m, 0.20 - 0.20 m, 0.30 - 0.30 m, 0.60 - 0.60 m, 2.00 - 2.00 m
		Soil Moisture Sensors: Meter-GS1, Meter-Teros10, Meter-Teros12, 

	TERENO
		Abstract: Soil moisture network in Germany, There are 4 observatories: in Northeastern Germany- Lowlan Observatory coordinated by German Research Centre of Geosciences, in Harz/Central Germany-  Lowland Observatory coordinated by Helmholtz Centre for Environmental Research, in Eifel/Lower Rhine Valley- Observatory coordinated by Research Centre Juelich and in Bavarian Alps/pre-Alps- Obervatory coordinated by Karlsruhe Institute of Technology and German Center for Environmental Health
		Continent: Europe
		Country: Germany
		Stations: 5
		Status: running
Data Range: 

		Type: meteo
		Url: https://www.tereno.net/joomla/index.php/overview
		Variables: air temperature, precipitation, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.20 - 0.20 m, 0.50 - 0.50 m
		Soil Moisture Sensors: Stevens-Hydraprobe-Digital, 

	TWENTE
		Abstract: The Twente region in the east of the Netherlands hold a network that monitors since 2009 profile soil moisture and temperature at twenty locations mostly in the rural environment. In addition, intensive measurement campaigns have been performed in 2009, 2015, 2016, and 2017 at number of measurement locations as a part of MSc and PhD research. The development of the network infrastructure has been supported through various EU and NWO-funded projects, and forthcoming data has been successfully used for the validation of satellite derived surface soil moisture products. The early development of the network has been described in Dente et al. (2011), but over the years the design of the network has altered considerably with the most recent updates documented in Van der Velde et al. (2021). In 2019, the Twente network has been operational for more than a decade and with this deposit we would like to make this data freely and well documented available for use by the science and professional communities. An accompanying data paper is under development and will be submitted to Earth System Science Data journal, which provide additional background information.
		Continent: Europe
		Country: Netherlands
		Stations: 44
		Status: running
		Data Range: from 2009-01-01 
		Type: project
		Url: https://doi.org/10.5194/essd-15-1889-2023
		Variables: soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.10 - 0.10 m, 0.20 - 0.20 m, 0.40 - 0.40 m, 0.80 - 0.80 m
		Soil Moisture Sensors: Meter-5TM, 

	TxSON
		Abstract: 
		Continent: Americas
		Country: USA
		Stations: 41
		Status: running
		Data Range: from 2014-10-01 
		Type: project
		Url: http://www.beg.utexas.edu/research/programs/txson
		Variables: soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m
		Soil Moisture Sensors: Campbell-CS655, 

	UMBRIA
		Abstract: The soil moisture network of the Civil Protection Functional Centre (CFD Umbria), together with the Research Institute for Geo-Hydrological Protection and Consiglio Nazionale delle Ricerca (abbreviated CNR-IRPI)  is located near the city of Perugia at Lake Trasimeno in the middle of Italy and consists of 7 stations. Four of these seven stations come from the old Network CRN_IRPI which are now part of the UMBRIA Network. One station became operational in the year 2002 and is providing soil moisture measurements at 3 layers and additionaly precipitation and air temperature observations. Other 3 stations, became operational in the year 2007 collect soil moisture measurements at 3 depths. The observed variables are sampled each hour.
		Continent: Europe
		Country: Italy
		Stations: 13
		Status: running
		Data Range: from 2002-10-09 
		Type: project
		Url: http://www.cfumbria.it/; http://hydrology.irpi.cnr.it/
		Variables: air temperature, precipitation, soil moisture, 
		Soil Moisture Depths: 0.05 - 0.15 m, 0.15 - 0.25 m, 0.25 - 0.35 m, 0.35 - 0.45 m, 0.45 - 0.55 m
		Soil Moisture Sensors: DeltaT-ThetaProbe-ML3, Sentek-EnviroSCAN, Sentek-EnviroSMART, 

	UMSUOL
		Abstract: 
		Continent: Europe
		Country: Italy
		Stations: 1
		Status: running
		Data Range: from 2004-08-31 
		Type: project
		Url: http://www.arpa.emr.it/sim/
		Variables: soil moisture, 
		Soil Moisture Depths: 0.10 - 0.10 m, 0.25 - 0.25 m, 0.45 - 0.45 m, 0.70 - 0.70 m, 1.00 - 1.00 m, 1.35 - 1.35 m, 1.80 - 1.80 m
		Soil Moisture Sensors: Campbell-TDR100, 

	USCRN
		Abstract: Soil moisture NRT network USCRN (Climate Reference Network) in United States;the  datasets of 114 stations were collected and processed by the National Oceanicand Atmospheric Administration"s National Climatic Data Center (NOAA"s NCDC)
		Continent: Americas
		Country: USA
		Stations: 131
		Status: running
		Data Range: from 2009-06-09 
		Type: meteo
		Url: https://www.ncei.noaa.gov/access/crn/
		Variables: air temperature, precipitation, soil moisture, soil temperature, surface temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.10 - 0.10 m, 0.20 - 0.20 m, 0.50 - 0.50 m, 1.00 - 1.00 m
		Soil Moisture Sensors: Stevens-Hydraprobe-Digital, 

	VDS
		Abstract: These networks have been installed to validate satellite soil moisture products over complex tropical regions.
		Continent: Asia
		Country: Myanmar
		Stations: 4
		Status: running
		Data Range: from 2017-06-01 
		Type: project
		Url: https://www.vandersat.com/
		Variables: soil moisture, soil temperature, 
		Soil Moisture Depths: 0.01 - 0.10 m, 0.10 - 0.10 m, 0.20 - 0.20 m
		Soil Moisture Sensors: Meter-GS1, Meter-Teros12, 

	WATERLINE
		Abstract: 
		Continent: Europe
		Country: Greece
		Stations: 3
		Status: running
		Data Range: from 2021-07-10 
		Type: Project
		Url: https://www.chistera.eu/projects/waterline
		Variables: air temperature, soil moisture, 
		Soil Moisture Depths: 0.05 - 0.05 m
		Soil Moisture Sensors: Sentek-DaD, 

	WEGENERNET
		Abstract: The WegenerNet Feldbach Region is a unique weather and climate observation network comprising more than 150 hydrometeorological stations measuring temperature, humidity, precipitation, and at 14 locations also wind speed and direction. Soil moisture and soil temperature are measured at 12 stations, which are part of the International Soil Moisture Network (ISMN). 


The stations are located in a tightly spaced grid within a core area of 22 km x 16 km centered near the city of Feldbach in southeastern Austria.
With about one station every two square-km (area of about 300 square-km in total), and each station with 5-min time sampling, the network provides fully automated regular measurements since January 2007.


************************************************************************************************************
IMPORTANT NOTE: All data is on version 8.0 For further details please see https://wegenernet.org/downloads/Fuchsberger-etal_2023_WPSv8-release-notes.pdf

************************************************************************************************************

		Continent: Europe
		Country: Austria
		Stations: 13
		Status: running
		Data Range: from 2007-01-01 
		Type: project
		Url: http://www.wegenernet.org/;http://www.wegcenter.at/wegenernet
		Variables: air temperature, precipitation, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.20 - 0.20 m, 0.30 - 0.30 m
		Soil Moisture Sensors: pF-meter, Stevens-Hydraprobe-Digital, 

	WIT-Network
		Abstract: 
		Continent: Asia
		Country: Pakistan
		Stations: 13
		Status: running
		Data Range: from 2022-04-04 
		Type: project
		Url: https://wit.lums.edu.pk/
		Variables: soil moisture, soil temperature, 
		Soil Moisture Depths: 0.10 - 0.10 m, 0.15 - 0.15 m
		Soil Moisture Sensors: Meter-EC5, WZ-SM, 

	WSMN
		Abstract: The WSMN network is located in Wales, Great Britain, and consists of six stations. The datasets are collected by the Aberystwyth University and are available since September 2011.
		Continent: Europe
		Country: UK
		Stations: 8
		Status: running
		Data Range: from 2013-07-11 
		Type: project
		Url: http://www.aber.ac.uk/wsmn
		Variables: soil moisture, soil temperature, 
		Soil Moisture Depths: 0.02 - 0.02 m, 0.05 - 0.05 m, 0.10 - 0.10 m
		Soil Moisture Sensors: Campbell-CS615, Campbell-CS616, Campbell-CS655, 

	XMS-CAT
		Abstract: The soil monitoring network is a set of stations with continuous data recording of physics parameters (temperature and moisture of soil) and environmental parameters such as pluviometry, temperature, relative air humidity and solar radiation. Project started at Tremp basin’s, in the crops of vineyards, and it has been continued in high altitude vineyard form Pre-pyrenees and Pyrenees. The main features that set up the stations are the sensors installed into the soils and the basic operation elements, such as the acquisition data system, the power system and the data transmission system. Generally, there are 4 multi parametric sensors to 5, 20, 50 and 100 cm of depth, when parent material allows it, these sensors measure soil moisture and temperature. Each station also has environmental sensors such as a rain gauge, a pyranometer and a air temperature and relative humidity probes for the necessary comparison of the soil and environmental parameters.
		Continent: Europe
		Country: Spain
		Stations: 22
		Status: running
		Data Range: from 2016-08-01 
		Type: project
		Url: https://visors.icgc.cat/mesurasols/#9/42.1765/1.1132
		Variables: air temperature, precipitation, soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.10 - 0.10 m, 0.20 - 0.20 m, 0.30 - 0.30 m, 0.40 - 0.40 m, 0.50 - 0.50 m, 0.60 - 0.60 m, 0.70 - 0.70 m, 0.75 - 0.75 m, 0.90 - 0.90 m, 1.00 - 1.00 m
		Soil Moisture Sensors: Campbell-CS655, Campbell-SoilVUE10, DeltaOhm-HD3910, 

	YJG-SM
		Abstract: 
		Continent: Asia
		Country: China
		Stations: 11
		Status: running
		Data Range: from 2024-07-25 
		Type: Project
		Url: 
		Variables: soil moisture, soil temperature, 
		Soil Moisture Depths: 0.05 - 0.05 m, 0.10 - 0.10 m
		Soil Moisture Sensors: Meter-Teros11, 

