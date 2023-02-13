import os
import piexif
import streamlit as st
import zipfile
import requests
import numpy as np
import pandas as pd
import pydeck as pdk
import geopandas as gpd
import matplotlib.pyplot as plt
import utm
import math
import xmltodict
from shapely.geometry import Polygon, MultiPolygon
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

def convert2egm(points):
    egm96_file = 'us_nga_egm96_15.tif'
    
    final_points = []
    with st.spinner('Converting from ellipsoidal to orthoetric...'):
        for la, lo, h in points:
            h_masl = h - interpolate_raster(egm96_file, la, lo)
            final_points.append((la, lo, h_masl))
        
    st.success('Preliminary Conversion Finished.')
    
    return final_points

def get_elevation(points, ppk):   
    lat = [x for x, y, z in points]
    lon = [y for x, y, z in points]
    
    if ppk:
         points_new = convert2egm(points)
         points = points_new
    
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

def generate_footprint(lat, lon, agl, roll, pitch, yaw):
    img_param = [35.8, 23.9, 35, 0]
    utm_conv = utm.from_latlon(lat, lon)
    utm_points = (utm_conv[0], utm_conv[1])
    utm_zone1 = utm_conv[2]
    utm_zone2 = utm_conv[3]
    
    sensor_x = img_param[0]
    sensor_y = img_param[1]
    f = img_param[2]
        
    hfv = 2*math.atan(sensor_x/(2*f))
    vfv = 2*math.atan(sensor_y/(2*f))
    
    foot = []
    for y in range(0,4):
        if y == 0:
            dx = math.tan(hfv/2 + pitch)*agl
            dy = math.tan(vfv/2 + roll)*agl
            dutm_x = dx*math.cos(yaw) - dy*math.sin(yaw)
            dutm_y = -dx*math.sin(yaw) - dy*math.cos(yaw)
            utm_x = utm_points[0] + dutm_x
            utm_y = utm_points[1] + dutm_y
            
            lat_point = utm.to_latlon(utm_x, utm_y, utm_zone1, utm_zone2)[0]
            lon_point = utm.to_latlon(utm_x, utm_y, utm_zone1, utm_zone2)[1]
            foot.append([lon_point, lat_point])
            
        elif y == 1:
            dx = math.tan(-hfv/2 + pitch)*agl
            dy = math.tan(vfv/2 + roll)*agl
            dutm_x = dx*math.cos(yaw) - dy*math.sin(yaw)
            dutm_y = -dx*math.sin(yaw) - dy*math.cos(yaw)
            utm_x = utm_points[0] + dutm_x
            utm_y = utm_points[1] + dutm_y
            
            lat_point = utm.to_latlon(utm_x, utm_y, utm_zone1, utm_zone2)[0]
            lon_point = utm.to_latlon(utm_x, utm_y, utm_zone1, utm_zone2)[1]
            foot.append([lon_point, lat_point])    
            
        elif y == 2:
            dx = math.tan(-hfv/2 + pitch)*agl
            dy = math.tan(-vfv/2 + roll)*agl
            dutm_x = dx*math.cos(yaw) - dy*math.sin(yaw)
            dutm_y = -dx*math.sin(yaw) - dy*math.cos(yaw)
            utm_x = utm_points[0] + dutm_x
            utm_y = utm_points[1] + dutm_y
            
            lat_point = utm.to_latlon(utm_x, utm_y, utm_zone1, utm_zone2)[0]
            lon_point = utm.to_latlon(utm_x, utm_y, utm_zone1, utm_zone2)[1]
            foot.append([lon_point, lat_point])  
            
        elif y == 3:
            dx = math.tan(hfv/2 + pitch)*agl
            dy = math.tan(-vfv/2 + roll)*agl
            dutm_x = dx*math.cos(yaw) - dy*math.sin(yaw)
            dutm_y = -dx*math.sin(yaw) - dy*math.cos(yaw)
            utm_x = utm_points[0] + dutm_x
            utm_y = utm_points[1] + dutm_y
            
            lat_point = utm.to_latlon(utm_x, utm_y, utm_zone1, utm_zone2)[0]
            lon_point = utm.to_latlon(utm_x, utm_y, utm_zone1, utm_zone2)[1]
            foot.append([lon_point, lat_point])
        
    poly = Polygon(foot)
    
    return poly

def correct_altitude(points, images, flag, ppk):
    new_folder = os.path.join('AGL_OUTPUT')
    lat = [x for x, y, z in points]
    lon = [y for x, y, z in points]
    names = [image.name for image in images]
    
    if not os.path.exists(new_folder):
        os.makedirs(new_folder)
    
    corrected_elev = get_elevation(points, ppk)
    
    footprints = []
    
    if flag:
        with st.spinner('Calculating image footprints...'):
            for x, elev in enumerate(corrected_elev):          
                with Image.open(images[x]) as img:
                    exif_data = piexif.load(img.info['exif'])     
                    exif_data['GPS'][6] = (int(elev * 100), 100)         
                    new_image_path = os.path.join(new_folder, 'AGL_' + images[x].name)            
                    new_exif = exif_data
                    exif_bytes = piexif.dump(new_exif)
                    img.save(new_image_path, exif=exif_bytes)
                    
                    temp = img.applist
                    d = str(temp[1][1])
                        
                    xmp_start = d.find('<x:xmpmeta')
                    xmp_end = d.find('</x:xmpmeta')
                    xmp_str = d[xmp_start:xmp_end+12]
                    
                    xmp = xmltodict.parse(xmp_str)
                    
                    roll = float(xmp['x:xmpmeta']['rdf:RDF']['rdf:Description']['@Camera:Roll'])*(math.pi/180)
                    pitch = float(xmp['x:xmpmeta']['rdf:RDF']['rdf:Description']['@Camera:Pitch'])*(math.pi/180)
                    yaw = float(xmp['x:xmpmeta']['rdf:RDF']['rdf:Description']['@Camera:Yaw'])*(math.pi/180)
                    
                    footprints.append(generate_footprint(lat[x], lon[x], elev, roll, pitch, yaw))
        
        st.success('Image Footprints Generated.')
        footprints_geom = list(MultiPolygon(footprints).geoms)
        footprints_gdf = gpd.GeoDataFrame(list(zip(names,lat,lon,corrected_elev,footprints_geom)), index=range(len(images)), 
                                          columns=['Image', 'Latitude', 'Longitude', 'AGL', 'geometry'], crs="EPSG:4326")
    else:
        footprints_gdf = gpd.GeoDataFrame()
    
    return new_folder, corrected_elev, footprints_gdf

def create_zip_file(folder, geotags, prints, flag):
    zip_file_path = 'AGL_OUTPUT.zip'
    
    csv_name = '_'.join(geotags['# image name' ][0].split('_')[:-1])+'_AGL.csv'
    shp_name = '_'.join(geotags['# image name' ][0].split('_')[:-1])+'_FOV.shp.zip'
    
    with st.spinner('Zipping file outputs...'):
        with zipfile.ZipFile(zip_file_path, 'w') as myzip:
            myzip.writestr(csv_name, geotags.to_csv(index=False).encode('utf-8'))
            if flag:
                prints.to_file(shp_name, driver='ESRI Shapefile')
                myzip.write(shp_name)
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
        
        geotagging = st.selectbox('Select Geotagging Type:', 
                                 ('<Select>',
                                  'PPK Geotagging',
                                  'Non-PPK Geotagging'))
                    
        ppk = True
        if geotagging != '<Select>':
            st.write(geotagging + ' selected.')
            if geotagging == 'Non-PPK Geotagging':
                ppk = False
        else:
            st.stop()
        
        fname = '# image name'              
        lat = 'latitude [decimal degrees]'
        lon = 'longitude [decimal degrees]'
        hgt = 'altitude [meter]'
        if image_flag:
            geotags = geotags_all[geotags_all[fname].isin(included_images)]
        else:
            geotags = geotags_all.copy()
        
        points = list(zip(geotags[lat], geotags[lon], geotags[hgt]))
    
        if st.button('CONVERT TO AGL'):
            folder, elev, prints = correct_altitude(points, imgs, image_flag, ppk)
            
            if image_flag:
                new_names = ['AGL_'+x for x in geotags[fname].tolist()]
                geotags[fname] = new_names
            
            geotags[hgt] = elev
            geotags.rename(columns={hgt:'AGL [meter]'}, inplace=True)
            
            points_df = pd.DataFrame(data=points, columns=['lat', 'lon', 'alt'])
            
            with st.spinner('Visualizing Data...'):
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
                         'GeoJsonLayer',
                         data=prints['geometry'],
                         get_fill_color='[39, 157, 245]',
                         get_line_color='[39, 157, 245]',
                         opacity=0.1,
                         pickable=True,
                     ),
                     pdk.Layer(
                         'ScatterplotLayer',
                         data=points_df,
                         opacity=0.7,
                         get_position='[lon, lat]',
                         get_color='[0,0,0]',
                         get_radius=5,
                         pickable=True
                     ),
                     ],        
                 ))
                
                fig, ax = plt.subplots()
                fig.set_size_inches(5, 2)
                ax.plot(range(1,len(geotags)+1), geotags['AGL [meter]'])
                ax.tick_params(axis='both', which='major', labelsize=5)
                ax.set_xlabel('Image #', size=5)
                max_x = len(geotags)+1
                if max_x > 40:
                    x_step = 10**(len(str(max_x))-1)
                else:
                    x_step = 1
                ax.set_xticks(range(1,max_x, x_step))
                ax.set_ylabel('AGL (meters)', size=5)
                max_y = int(geotags['AGL [meter]'].max()+10)
                ax.set_yticks(range(0, max_y, int(max_y/10)))
                st.pyplot(fig)
            
            zip_path = create_zip_file(folder, geotags, prints, image_flag)
            
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
