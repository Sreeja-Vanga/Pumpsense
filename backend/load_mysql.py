import os,pymysql
c=pymysql.connect(host=os.getenv('DB_HOST','127.0.0.1'),user=os.getenv('DB_USER','root'),password=os.getenv('DB_PASSWORD',''),autocommit=True); cur=c.cursor(); db=os.getenv('DB_NAME','pumpsense')
cur.execute(f'DROP DATABASE IF EXISTS {db}'); cur.execute(f'CREATE DATABASE {db} CHARACTER SET utf8mb4'); cur.execute(f'USE {db}')
for f in ['schema.sql',os.path.join(os.getenv('DATA','data'),'seed.sql')]:
  for st in open(f,encoding='utf8').read().split(';\n'):
    st='\n'.join(l for l in st.splitlines() if not l.strip().startswith('--')).strip()
    if st: cur.execute(st)
print('loaded into',db)