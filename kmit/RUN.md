# 실행 순서

```bash
# 1. 데이터 수집 (최초 1회)
python3 vworld_fetcher.py
python3 osm_fetcher.py

# 2. USD 생성
python3 main.py

# 3. 텍스처 적용
python3 apply_textures.py gumi.usda

# 4. 뷰어
~/Downloads/bin/usdview gumi.usda
```
