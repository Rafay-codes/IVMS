```bash
pip install -r ./requirements.txt

sudo apt-get install libssl-dev openssl libmysqlclient21 libmysqlclient-dev mysql-server mysql-client mysql-common pkg-config cmake-data phpmyadmin php-mbstring php-zip php-gd php-json php-curl
sudo systemctl enable mysql.service
sudo systemctl start mysql.service

pip install mysqlclient
sudo mysql
mysql> ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'Passme@1879';
sudo mysql_secure_installation
mysql -u root -p
mysql> CREATE USER 'nvidia'@'localhost' IDENTIFIED WITH authentication_plugin BY 'Passme@1879';
mysql> CREATE USER 'nvidia'@'localhost' IDENTIFIED BY 'Passme@1879';
mysql> CREATE DATABASE IVMS_DB;
mysql> GRANT ALL PRIVILEGES ON *.* TO 'nvidia'@'localhost' WITH GRANT OPTION;
mysql> FLUSH PRIVILEGES;
mysql> exit;

python manage.py migrate
python manage.py makemigrations
python manage.py createsuperuser
gunicorn django_project.wsgi --bind 0.0.0.0:8000
```
Other helpful commands:  
```bash
# mysql> GRANT PRIVILEGE ON IVMS_DB TO 'nvidia'@'localhost';
# mysql> GRANT CREATE, ALTER, DROP, INSERT, UPDATE, INDEX, DELETE, SELECT, REFERENCES, RELOAD on *.* TO 'nvidia'@'localhost' WITH GRANT OPTION;
sudo apt-get purge mysql-server mysql-client mysql-common mysql-server-core-* mysql-client-core-*
sudo rm -rf /etc/mysql /var/lib/mysql
sudo apt-get autoremove
sudo apt-get autoclean

phpmyadmin
sudo cp /etc/phpmyadmin/apache.conf /etc/apache2/conf-available/phpmyadmin.conf
sudo a2enconf phpmyadmin
sudo service apache2 restart

python manage.py startapp <new-app-name>
python manage.py runserver
python manage.py runserver 8080
python manage.py runserver 0.0.0.0:8000
python manage.py migrate
python manage.py makemigrations <new-app-name>
python manage.py sqlmigrate polls 0001

```
