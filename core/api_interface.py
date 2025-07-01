import os
import requests

from utils.yaml_parser import YamlParser


class APIInterface():
    def __init__(self, cfg, configs_dir):
        self.base_url = cfg.API.PATHS.BASE_URL
        self.login_endpoint = cfg.API.PATHS.AUTH
        self.list_event_status_endpoint = cfg.API.PATHS.STATUS
        self.list_violation_types_endpoint = cfg.API.PATHS.VIOLATION_TYPES
        self.event_detail_endpoint = cfg.API.PATHS.EVENTS
        self.plate_detail_endpoint = cfg.API.PATHS.PLATES

        # Get credentials from YAML file
        self.creds_path = os.path.join(configs_dir, cfg.API.PATHS.CREDS_FILE)
        self.credentials = YamlParser(config_file=self.creds_path)
        self.token = self.credentials.Token
        self.user = self.credentials.User
        self.pswd = self.credentials.Pass
        self.cookie = None
        #print(self.token, self.user, self.pswd)
        self.update_token()
        #print('csrftoken={0}; sessionid={1}'.format(self.cookie["csrftoken"], self.cookie["sessionid"]))
        
    # Authenticate the user by using creds from the yaml file
    def update_token(self):    
        user_data = {
            'username': self.user,
            'password': self.pswd
        }
        try:
            response = requests.post(self.base_url + 
                                    self.login_endpoint,
                                    json=user_data)
            #print(response.json())
            self.token = response.json()['key']
            self.cookie = response.cookies
            #print(self.token)
        except Exception as e:
            print("An error has occured", e)

    def set_token_in_header(self, headers):
        # headers = {
        #     'Authorization': f'Token {token}'
        # }
        #headers['Authorization'] = 'Bearer ' + self.token
        headers['X-CSRFToken'] = self.cookie["csrftoken"]
        headers['Cookie'] = "csrftoken={0}; sessionid={1}".format(self.cookie["csrftoken"], self.cookie["sessionid"])
        return headers
    
    def get_eventstatus_id(self, status='Recorded'):
        headers = {}
        headers = self.set_token_in_header(headers)
        status_id = -1
        try:
            response = requests.get(self.base_url + self.list_event_status_endpoint,
                                     headers=headers)
            #print(response)
            #print(response.json())
            response.raise_for_status()
            if response.status_code == 200:
                data = response.json()
                for item in data:
                    if item['status'] == status:
                        status_id = item['id']

        except Exception as e:
            print("An error occured:", e)
        return status_id
    
    def get_eventviolationtype_id(self, violation_type='mobile'):
        headers = {}
        headers = self.set_token_in_header(headers)
        violation_type_id = -1
        try:
            response = requests.get(self.base_url + self.list_violation_types_endpoint,
                                     headers=headers)
            #print(response)
            #print(response.json())
            response.raise_for_status()
            if response.status_code == 200:
                data = response.json()
                for item in data:
                    if item['violationType'] == violation_type:
                        violation_type_id = item['id']

        except Exception as e:
            print("An error occured:", e)
        return violation_type_id
    
    def update_plate_event(self, cropped_fname:str, plate_num:str, plate_type:int, plate_state:str, plate_country:str):
        headers = {}
        headers = self.set_token_in_header(headers)
        print(headers)
        
        compiled_endpoint = self.plate_detail_endpoint #+ str(event_id) + '/'
        data = {
                'image_path': cropped_fname,
                "plate_num": plate_num,
                "plate_type": plate_type,
                "plate_state": plate_state,
                "plate_country": plate_country
            }
        try:      
            response = requests.post(self.base_url + compiled_endpoint, json=data, headers=headers)
            print(response)
            #print(response.json())
            response.raise_for_status()

        except Exception as e:
            print("An error occured:", e)
            
    def update_event(self, event_id, recording_path, event_violation_type):      
        headers = {}
        headers = self.set_token_in_header(headers)
        # TODO find a better way to get id? Hardcoding string is the solution for now
        recorded_status_id = self.get_eventstatus_id('Recorded')
        violation_type_id = self.get_eventviolationtype_id(event_violation_type)
        
        compiled_endpoint = self.event_detail_endpoint #+ str(event_id) + '/'
        data = {
                'statusId': recorded_status_id,
                'recordingPath': recording_path,
                'violationTypeId': violation_type_id,
                "plateNum": "-",
                "plateType": "-",
                "plateState": "-"
            }
        try:      
            response = requests.post(self.base_url + compiled_endpoint, json=data, headers=headers)
            print(response)
            #print(response.json())
            response.raise_for_status()

        except Exception as e:
            print("An error occured:", e)
