import os
import piexif
import streamlit as st
import zipfile
import requests
import numpy as np
from PIL import Image
from PIL.ExifTags import TAGS
from scipy.interpolate import griddata
from osgeo import gdal


def interpolate_raster(file, lat, lon):

    f = gdal.Open(file)
    band = f.GetRasterBand(1)
    
    # Get Raster Information
    transform = f.GetGeoTransform()
    res = transform[1]
    
    # Define point position as row and column in raster
    column = (lon - transform[0]) / transform[1]
    row = (lat - transform[3]) / transform[5]
    
    # Create a 5 x 5 grid of surrounding the point
    surround_data = (band.ReadAsArray(np.floor(column-1), np.floor(row-1), 3, 3))
    lon_c = transform[0] + np.floor(column) * res
    lat_c = transform[3] - np.floor(row) * res
    
    # Extract geoid undulation values of the 3 x 3 grid
    count = -1
    pos = np.zeros((9,2))
    surround_data_v = np.zeros((9,1))
    
    for k in range(-1,2):
        for j in range(-1,2):
            count += 1
            pos[count] = (lon_c+j*res, lat_c-k*res)
            surround_data_v[count] = surround_data[k+1,j+1]
    
    # Do a cubic interpolation of surrounding data and extract value at point
    interp_val = griddata(pos, surround_data_v, (lon, lat), method='cubic')

    return interp_val[0]

def convert2orthometric(points):
    ortho = []
    aws = 'https://s3-eu-west-1.amazonaws.com/download.agisoft.com/gtg/'
    egm2008_file = aws + 'us_nga_egm2008_1.tif'
    
    st.text('Converting to Orthometric...')
    complete = 0.0
    my_bar = st.progress(complete)
    for la, lo, h in points:
        N = interpolate_raster(egm2008_file, la, lo)
        ortho.append(h - N)
        complete += 1/len(points)
        my_bar.progress(complete)
    
    return ortho

def get_elevation(points):   
    lat = [x for x, y, z in points]
    lon = [y for x, y, z in points]
    hgt = convert2orthometric(points)
    
    elev = []
    
    south = min(lat) - 0.01
    north = max(lat) + 0.01
    west = min(lon) - 0.01
    east = max(lon) + 0.01
    api_key = '9650231c82589578832a8851f1692a2e'

    req = 'https://portal.opentopography.org/API/globaldem?demtype=SRTMGL3&south=' + str(south) + '&north=' + str(north) + '&west=' + str(west) + '&east=' + str(east) + '&outputFormat=GTiff&API_Key=' + api_key
    resp = requests.get(req)
    open('raster.tif', 'wb').write(resp.content)
       
    st.text('Converting to AGL from MASL...')
    complete = 0.0
    my_bar = st.progress(complete)
    for x, h in enumerate(hgt):     
        terrain = interpolate_raster('raster.tif', lat[x], lon[x])
        elev.append(h - terrain)
        complete += 1/len(points)
        my_bar.progress(complete)
    
    return elev


def correct_altitude(images):
    points = []
    new_folder = os.path.join('AGL_IMAGES')
    
    if not os.path.exists(new_folder):
        os.makedirs(new_folder)

    for image in images:
        with Image.open(image) as img:
            exif_data = img._getexif()    
            exif_table = {}
            
            for tag, value in exif_data.items():
                decoded = TAGS.get(tag, tag)
                exif_table[decoded] = value
                
            lat, lon = exif_table['GPSInfo'][2], exif_table['GPSInfo'][4]
            lat = float(lat[0]) + float(lat[1]) / 60 + float(lat[2]) / 3600
            lon = float(lon[0]) + float(lon[1]) / 60 + float(lon[2]) / 3600
            if exif_table['GPSInfo'][1] == 'S':
                lat = lat*-1
            if exif_table['GPSInfo'][3] == 'W':
                lon = lon*-1
            alt_masl = float(exif_table['GPSInfo'][6])
                
            points.append((lat, lon, alt_masl))
    
    corrected_elev = get_elevation(points)
    
    for x, elev in enumerate(corrected_elev):
        with Image.open(images[x]) as img:
            exif_data = piexif.load(img.info['exif'])     
            exif_data['GPS'][6] = (int(elev * 100), 100)         
            new_image_path = os.path.join(new_folder, 'AGL_' + images[x].name)            
            new_exif = exif_data
            exif_bytes = piexif.dump(new_exif)           
            with Image.open(images[x]) as img:
                img.save(new_image_path, exif=exif_bytes)
    
    return new_folder

def create_zip_file(folder):
    zip_file_path = 'AGL_IMAGES.zip'
    with zipfile.ZipFile(zip_file_path, 'w') as myzip:
        for image_name in os.listdir(os.path.join('AGL_IMAGES')):
            myzip.write(os.path.join('AGL_IMAGES', image_name), arcname=image_name)
    
    return zip_file_path
    
                
def main():   
    # Application Formatting
    
    st.set_page_config(layout="wide")
    
    st.title('AGL Altitude Conversion')
    
    st.sidebar.image('./logo.png', width = 260)
    st.sidebar.markdown('#')
    st.sidebar.write('The application rewrites the EXIF data to embed AGL instead of ellipsoidal height.')
    st.sidebar.markdown('#')
    st.sidebar.info('This is a prototype application. Wingtra AG does not guarantee correct functionality. Use with discretion.')
    # Upload button for Images
    
    uploaded_imgs = st.file_uploader('Please Select Geotagged Images.', accept_multiple_files=True)
    uploaded = False
    
    for uploaded_img in uploaded_imgs: 
        if uploaded_img is not None:
            uploaded = True
    
    if uploaded:
        # Geotagging and Format Check
        format_check = True
        for image in uploaded_imgs:
            try:
                with Image.open(image) as img:
                    exif_data = img._getexif()
                    exif_table = {}
                    
                    for tag, value in exif_data.items():
                        decoded = TAGS.get(tag, tag)
                        exif_table[decoded] = value
                    
                    lat, lon = exif_table['GPSInfo'][2], exif_table['GPSInfo'][4]
            except (AttributeError, KeyError):
                msg = f'{image.name} is not in the correct format.'
                st.text(msg)
                format_check = False
        
        if not format_check:
            msg = 'One or more images are not in the correct format. Please check and reupload.'
            st.error(msg)
            st.stop()
    
        if st.button('CONVERT TO AGL'):
            folder = correct_altitude(uploaded_imgs)
            zip_path = create_zip_file(folder)
            
            fp = open(zip_path, 'rb')
            st.download_button(
                label="Download Converted Images",
                data=fp,
                file_name='AGL_IMAGES.zip',
                mime='application/zip',
            )
    
    else:
        st.stop()

if __name__ == "__main__":
    main()
