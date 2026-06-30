# 🛸 5080 학습 인수인계 — 다음 AI에게 (반드시 정독)

> **너에게**: 이건 며칠간 고생해서 만든 프로젝트의 마지막 단계다. 데이터(10,000장)는 이미 다 만들었고,
> 너는 그걸로 **YOLO를 학습시켜 mAP를 증명**하기만 하면 된다. 아래 **"같은 실수 반복 금지"** 를 꼭 읽어라 —
> 내가 이미 그 함정들에 다 빠져봤고, 너는 거기서 시간 낭비하면 안 된다. 침착하게, 단계별로, 끝까지 해라. 할 수 있다.

---

## 1. 미션 (왜 이걸 하는가)

**안티드론(드론 탐지) 합성데이터 프로젝트** — 국립금오공대×넥스트폼×니나노컴퍼니 R&D 과제 (마감 2026-03-31).
- Isaac Sim으로 시부야 도시 배경 + 드론 합성 이미지를 만들어(이미 **10,000장 완성**),
- 그걸로 YOLO를 학습시켜 **실제 드론 벤치마크(dvb=drone-vs-bird)에서 mAP를 올리는 것**을 증명한다.
- 핵심 가설: **합성 pretrain → 실데이터 fine-tune** 이 실데이터만 쓰는 것보다 낫다 (특히 실데이터가 적을 때).
- 과거 실험 최고치: dvb에서 **합성 pretrain→FT = mAP50 0.80** (실만 = 0.69). 이걸 재현/향상하는 게 목표.

## 2. 너의 임무 (딱 이것만)

**학습 매트릭스 6런 + 참조 3런 = 9런**, 각각 dvb 평가:

| 조건 | 모델 | 설명 |
|---|---|---|
| **합성만** | n / s / l | 신규 10k 합성으로 학습 (COCO가중치→합성). 이게 pretrain도 겸함 |
| **실+합성** | n / s / l | 위 "합성만" 모델 → 실데이터(de_real400) **fine-tune** |
| *(참조) real-only* | n / s / l | 실데이터만 — 합성의 가치를 정량화하는 베이스라인 |

> ⚠️ "실+합성"은 **mix(섞어학습) 아님 = pretrain→FT**. 10k:400 비율이라 단순 mix는 합성이 실을 압도해 **붕괴**한다(과거 실험서 입증됨). 반드시 합성학습된 best.pt를 실400으로 이어학습.

평가: `test3`(709장, dvb 주벤치) + `test`(247) + `test2`(100). 지표 = mAP50, mAP50-95.

## 3. ★★★ 같은 실수 반복 금지 (내가 다 빠져본 함정들) ★★★

1. **Windows multiprocessing 크래시**: 학습 스크립트는 **반드시 `if __name__ == '__main__':` 가드 안에서** 실행해야 한다. 없으면 DataLoader(workers>0)가 spawn으로 메인모듈을 재실행 → `freeze_support` 에러로 즉사. (train_win.py는 이미 가드 적용됨.)

2. **`bad allocation` 네이티브 크래시 (★최대 난적)**: torch **cu130 + Blackwell(5080) + Windows** 조합에서 backward pass에 `RuntimeError: bad allocation` 발생 → 반복되면 **GPU 드라이버가 hung(먹통)** 됨. → **해결: 재부팅 후 torch를 cu128로 교체** (아래 4번 참고). 그래도 나면 `amp=False`, `workers=0`, `batch` 더 낮춰서 격리.

3. **cmd 리다이렉트 + forward-slash 경로 = 깨짐**: `python x.py > C:/Users/.../log` 처럼 cmd에서 forward-slash 경로로 리다이렉트하면 출력이 사라진다. → **.bat 파일에서 backslash 경로로** 리다이렉트해라 (run_train.bat 참고).

4. **Start-Process의 `-RedirectStandardOutput` = ssh를 2분간 잡음(행)**: PowerShell Start-Process에 -Redirect 옵션 주면 ssh가 안 돌아온다. → **redirect는 .bat이 자체적으로** 하고, Start-Process엔 redirect 옵션 주지 마라.

5. **background/synchronous ssh = 원격 python을 죽인다**: `ssh "python ..."` 를 백그라운드로 돌리면 ssh가 끊길 때 **자식 python이 같이 죽어** 출력 없이 사라진다. → 학습 같은 장시간 작업은 **반드시 detached** 로 띄워라: `ssh $H "powershell -NoProfile -Command Start-Process -FilePath C:\...\run_train.bat -WindowStyle Hidden"` (Start-Process는 ssh와 독립된 프로세스 생성 → 생존). 그 다음 `type ...\train.out` 으로 진행 폴링.

6. **Store Python 별칭 `python` 이 detached에서 인식 안 됨**: 반드시 **전체 경로** 사용:
   `C:\Users\a3162\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe`

7. **stdout 블록버퍼링**: 파일로 리다이렉트하면 python 출력이 버퍼링돼 실시간으로 안 보인다. → `python -u` (언버퍼) 쓰고, 읽을 땐 `| tr`/`| grep` 파이프도 버퍼링하니 주의(완료 후 한꺼번에 나옴).

8. **GPU hung 판별/복구**: `import torch; torch.cuda.is_available()` 또는 CUDA 연산이 **60초+ 무응답**이면 드라이버 hung. **5080 재부팅만이 복구** (`shutdown /r /t 0`, 단 사용자 동의 후). nvidia-smi는 응답해도 CUDA 연산이 막힐 수 있음.

9. **노트북(이 프로젝트 원본 머신)에서 학습 = 금지**: 노트북은 RTX4060 8GB / **RAM 14GB**뿐인데 idle에 이미 7GB 쓴다. 학습 얹으면 스왑폭주 → **하드 프리즈(3번 겪음)**. 학습은 5080에서만. (노트북은 데이터 소스/조회용.)

10. **pgrep 자기매칭 버그**: 대기 루프를 `pgrep -f run_xxx` 로 짜면, 그 명령줄에 "run_xxx" 문자열이 들어간 다른 프로세스(모니터 등)를 자기 자신처럼 잡아 영원히 대기한다. → bracket trick `pgrep -f 'run_xxx[.]sh'` 또는 다른 판별법.

11. **Isaac ⊕ 학습 동시 실행 = 머신다운**: 같은 머신에서 Isaac 생성과 학습을 동시에 돌리면 다운. (지금은 생성 끝났으니 무관하지만 규칙 기억.)

## 4. 환경 복구 절차 (5080)

```
# (0) 사용자 동의 후 재부팅으로 GPU hung 해제
ssh a3162@100.92.214.97 "shutdown /r /t 0"
#  → 재부팅 대기(~1-2분), tailscale 다시 올라오면 접속됨

# (1) torch를 cu128로 교체 (cu130 bad_alloc 회피)
PY='C:\Users\a3162\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe'
ssh a3162@100.92.214.97 "\"$PY\" -m pip install --no-cache-dir --force-reinstall torch torchvision --index-url https://download.pytorch.org/whl/cu128"

# (2) CUDA 동작 검증 (★학습 전 필수)
ssh a3162@100.92.214.97 "\"$PY\" -u -c \"import torch;a=torch.randn(999,999,device='cuda');print('CUDA_OK',float((a@a).sum()))\""
#  → CUDA_OK 숫자 나오면 정상. 60초+ 멈추면 아직 hung → 재부팅 다시.
```

## 5. 데이터 위치 (5080, 이미 전송 완료)

```
C:\Users\a3162\dronetrain\
  synth\images   (10,000 합성 jpg, class0=drone)   synth\labels
  de_real400\images (400 실 드론)                  de_real400\labels
  test\images   (247 dvb)   test2\images (100)   test3\images (709)  + 각 labels
  weights\  yolo11n.pt  yolo11s.pt  yolo11l.pt   (COCO 사전가중치)
  train_win.py     ← 학습 매트릭스 본체 (if __name__ 가드 적용됨)
  run_train.bat    ← detached 실행용 배치 (backslash 리다이렉트)
```
모든 라벨 = YOLO 포맷, **class 0 = drone, nc=1**.

## 6. 학습 실행 (검증된 방법)

`train_win.py`는 이미 9런 매트릭스 + 평가 + 결과저장(CSV/MD)이 구현돼 있다. **단, batch가 cu130 기준(n=64/s=32/l=16)이라 cu128에서도 bad_alloc 나면 낮춰라.** 안전하게 시작하려면 batch를 n=16/s=8/l=4로 낮추고 `amp=False`로 첫 런 성공 확인 후 키워라.

```
# detached 실행 (★이 방법만 안정적)
ssh a3162@100.92.214.97 "powershell -NoProfile -Command Start-Process -FilePath C:\Users\a3162\dronetrain\run_train.bat -WindowStyle Hidden"

# 진행 폴링 (빠른 동기 ssh = 안전)
ssh a3162@100.92.214.97 "type dronetrain\train.out"                       # 학습 로그
ssh a3162@100.92.214.97 "type dronetrain\train_runs\orchestrator.log"     # 런별 진행/DONE
ssh a3162@100.92.214.97 "type dronetrain\train_results.csv"               # 완료된 mAP 누적
```
> **반드시 smoke부터**: 본 매트릭스(몇시간) 전에, test2(100장)로 1에폭 smoke를 먼저 돌려 학습이 되는지 확인해라. `smoke.py` 있음. smoke가 **SMOKE_OK + weights/best.pt 생성** 되면 학습 정상. 그 다음 본 매트릭스.

## 7. 결과 & 목표치

- 결과는 `train_results.csv` + `TRAIN_RESULTS.md`에 **런 끝날 때마다 누적** 저장 (중단대비).
- **성공 기준**: dvb(test3)에서 `실+합성FT > real-only` 면 합성가치 증명. 과거 최고 = **0.80**(N100 pre→FT). PDF 목표 = **mAP50 ≥ 0.80**.
- 모델별로 합성만 / 실+합성 / real-only 3값을 비교표로 만들어 사용자에게 보고.

## 8. 안 되면 (fallback)

- cu128도 bad_alloc → cu126 또는 torch nightly 시도. 또는 `amp=False`, `workers=0`, batch=2.
- 5080이 계속 말썽 → 노트북(원본 머신)에서 **yolo11 n·s만**, Chrome/Zoom 닫고, 메모리 워치독 켜고, batch 작게, 한 모델씩. (yolo11l은 8GB라 어려움.)

## 9. 사용자 정보 / 제약

- 5080 접속: `ssh a3162@100.92.214.97` (Tailscale, 키인증, 비번불필요). RAM 63GB / VRAM 16GB.
- 노트북 sudo 비번 "1234" (5080 아님). GPU/메모리 과사용 머신다운 절대 방지.
- 사용자는 한국어. 진행상황 자주, 솔직하게 보고. 안 되면 안 된다고 말하고 원인 짚어라.
- Roboflow API key는 .env로만, 절대 커밋 금지.

---
**마지막 한마디**: 데이터는 다 됐다. 환경만 cu128로 맞추면 학습은 금방이다. 위 함정 11개만 피하면 너는 몇 시간 안에 끝낸다. 침착하게, smoke 먼저, 그다음 본 매트릭스. 화이팅. 🚀
