import os
import piexif
import streamlit as st
import zipfile
import requests
import numpy as np
import pandas as pd
import pydeck as pdk
import matplotlib.pyplot as plt
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
    
    # Create a 3 x 3 grid of surrounding the point
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

def get_elevation(points):   
    lat = [x for x, y, z in points]
    lon = [y for x, y, z in points]
    
    elev = []
    
    south = min(lat) - 0.01
    north = max(lat) + 0.01
    west = min(lon) - 0.01
    east = max(lon) + 0.01
    api_key = '9650231c82589578832a8851f1692a2e'

    
    with st.spinner('Converting from MASL to AGL...'):
        req = 'https://portal.opentopography.org/API/globaldem?demtype=SRTMGL3&south=' + str(south) + '&north=' + str(north) + '&west=' + str(west) + '&east=' + str(east) + '&outputFormat=GTiff&API_Key=' + api_key
        resp = requests.get(req)
        open('raster.tif', 'wb').write(resp.content)
           
        for la, lo, h in points:     
            terrain = interpolate_raster('raster.tif', la, lo)
            elev.append(h - terrain)
    
    st.success('Conversion Finished.')
    return elev


def correct_altitude(points, images, flag):
    new_folder = os.path.join('AGL_OUTPUT')
    
    if not os.path.exists(new_folder):
        os.makedirs(new_folder)
    
    corrected_elev = get_elevation(points)
    
    if flag:
        for x, elev in enumerate(corrected_elev):
            with Image.open(images[x]) as img:
                exif_data = piexif.load(img.info['exif'])     
                exif_data['GPS'][6] = (int(elev * 100), 100)         
                new_image_path = os.path.join(new_folder, 'AGL_' + images[x].name)            
                new_exif = exif_data
                exif_bytes = piexif.dump(new_exif)           
                with Image.open(images[x]) as img:
                    img.save(new_image_path, exif=exif_bytes)
    
    return new_folder, corrected_elev

def create_zip_file(folder, geotags, flag):
    zip_file_path = 'AGL_OUTPUT.zip'
    
    csv_name = '_'.join(geotags['# image name' ][0].split('_')[:-1])+'_AGL.csv'
    
    with st.spinner('Zipping file outputs...'):
        with zipfile.ZipFile(zip_file_path, 'w') as myzip:
            myzip.writestr(csv_name, geotags.to_csv(index=False).encode('utf-8'))
            if flag:
                for image_name in os.listdir(os.path.join('AGL_OUTPUT')):
                    myzip.write(os.path.join('AGL_OUTPUT', image_name), arcname=image_name)
                    
      
    st.success('Outputs are now ready for download.')
    return zip_file_path
    
                
def main():   
    # Application Formatting
    
    st.set_page_config(layout="wide")
    
    st.title('AGL Altitude Conversion')
    
    st.sidebar.image('./logo.png', width = 260)
    st.sidebar.markdown('#')
    st.sidebar.write('The application rewrites the EXIF data to embed AGL instead of ellipsoidal height.')
    st.sidebar.write('It requires the Geotags CSV and, if desired, the geotagged images as well.')
    st.sidebar.markdown('#')
    st.sidebar.info('This is a prototype application. Wingtra AG does not guarantee correct functionality. Use with discretion.')
    # Upload button for Images
    
    uploaded_files = st.file_uploader('Select all relevant files in the OUTPUT folder.', accept_multiple_files=True)
    uploaded = False
    
    for uploaded_file in uploaded_files: 
        if uploaded_file is not None:
            uploaded = True
            if uploaded_file.name.split('.')[-1] == 'csv':
                geotags_all = pd.read_csv(uploaded_file, index_col=False)
    
    if uploaded:
        # Geotagging and Format Check
        format_check = True
        points = []
        included_images = []
        image_flag = True
        
        imgs = [x for x in uploaded_files if x.name.split('.')[-1] == 'JPG']
        
        if len(imgs) == 0:
            st.write('No images uploaded. Only the geotags CSV will be converted')
            image_flag = False
        
        else:
            for image in imgs:         
                with Image.open(image) as img:
                    exif_data = img._getexif()
                    exif_table = {}
                    
                    for tag, value in exif_data.items():
                        decoded = TAGS.get(tag, tag)
                        exif_table[decoded] = value
                    
                    if 'GPSInfo' not in exif_table.keys():
                        msg = f'{image.name} is not in the correct format.'
                        st.text(msg)
                        format_check = False   
                        
                    included_images.append(image.name)
        
        if geotags_all.empty:
            st.text('No geotags CSV file uploaded.')
        if not format_check:
            msg = 'One or more files are not in the correct format or upload is incomplete. Please check and reupload.'
            st.error(msg)
            st.stop()
        elif format_check and image_flag:
            msg = f'Successfully uploaded {len(included_images)} images.'
            st.success(msg)
        else:
            msg = f'Geotags CSV successfully uploaded. There are {len(geotags_all)} captures.'
            st.success(msg)
        
        fname = '# image name'              
        lat = 'latitude [decimal degrees]'
        lon = 'longitude [decimal degrees]'
        hgt = 'altitude [meter]'
        if image_flag:
            geotags = geotags_all[geotags_all[fname].isin(included_images)]
        else:
            geotags = geotags_all.copy()
        
        points = list(zip(geotags[lat], geotags[lon], geotags[hgt]))
            
        points_df = pd.DataFrame(data=points, columns=['lat', 'lon', 'alt'])
        
        st.pydeck_chart(pdk.Deck(
        map_style='mapbox://styles/mapbox/satellite-streets-v11',
        initial_view_state=pdk.ViewState(
            latitude=points_df['lat'].mean(),
            longitude=points_df['lon'].mean(),
            zoom=14,
            pitch=0,
         ),
         layers=[
             pdk.Layer(
                 'ScatterplotLayer',
                 data=points_df,
                 get_position='[lon, lat]',
                 get_color='[70, 130, 180, 200]',
                 get_radius=20,
             ),
             ],
         ))
    
        if st.button('CONVERT TO AGL'):
            folder, elev = correct_altitude(points, imgs, image_flag)
            
            if image_flag:
                new_names = ['AGL_'+x for x in geotags[fname].tolist()]
                geotags[fname] = new_names
            
            geotags[hgt] = elev
            geotags.rename(columns={hgt:'AGL [meter]'}, inplace=True)
            
            fig, ax = plt.subplots()
            fig.set_size_inches(5, 2)
            ax.plot(range(1,len(geotags)+1), geotags['AGL [meter]'])
            ax.set_xlabel('Image #', size=5)
            max_x = len(geotags)+1
            ax.set_xticks(range(1,max_x, int(max_x/10)))
            ax.set_ylabel('AGL (meters)', size=5)
            max_y = int(geotags['AGL [meter]'].max()+10)
            ax.set_yticks(range(0, max_y, int(max_y/10)))
            st.pyplot(fig)
            
            zip_path = create_zip_file(folder, geotags, image_flag)
            
            fp = open(zip_path, 'rb')
            st.download_button(
                label="Download Outputs of Conversion",
                data=fp,
                file_name='AGL_OUTPUT.zip',
                mime='application/zip',
            )
    
    else:
        st.stop()

if __name__ == "__main__":
    main()
