import pandas as pd
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from concurrent.futures import ThreadPoolExecutor
from sklearn.preprocessing import StandardScaler
import torch
from transformers import AutoModel, AutoTokenizer
import time
import os

# 데이터 로드
df1 = pd.read_csv('C:/Users/minjeong/OneDrive/24-2/tripbeats/music/data/merged_data.csv')
df2 = pd.read_csv('C:/Users/minjeong/OneDrive/24-2/tripbeats/music/data/travel_hashtags_total.csv')

df1 = df1[:10]
df2 = df2.iloc[:10,2:]

# 해시태그 문자열을 리스트로 변환하고 각 해시태그에서 #을 제거하는 함수
def process_hashtags(hashtag_str):
    hashtag_str = hashtag_str.strip()
    hashtag_list = hashtag_str.split()
    return [tag.replace('#', '') for tag in hashtag_list]

# 모델과 토크나이저 로드
model_path = 'Alibaba-NLP/gte-large-en-v1.5'
tokenizer = AutoTokenizer.from_pretrained(model_path)
model = AutoModel.from_pretrained(model_path, trust_remote_code=True)

# GPU 사용 설정
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)

# 텍스트를 임베딩하는 함수 정의
def embed_text(text):
    batch_dict = tokenizer(text, max_length=8192, padding=True, truncation=True, return_tensors='pt')
    batch_dict = {k: v.to(device) for k, v in batch_dict.items()}  # 데이터를 GPU로 이동
    with torch.no_grad():
        outputs = model(**batch_dict)
    return outputs.last_hidden_state[:, 0].cpu().squeeze().numpy()  # 결과를 CPU로 다시 이동하고 첫 번째 토큰의 임베딩 벡터만 사용

# 리스트 형태의 텍스트 임베딩
def embed_text_list(text_list):
    with ThreadPoolExecutor() as executor:
        embeddings = list(executor.map(embed_text, text_list))
    return np.array(embeddings)

# 두 리스트의 텍스트 임베딩 간 거리 계산 및 평균 계산
def calculate_mean_distance(embeddings1, embeddings2):
    similarities = cosine_similarity(embeddings1, embeddings2)
    mean_distance = np.mean(similarities)
    return mean_distance, similarities

# 해시태그 열을 처리하여 #을 제거
df1['generated'] = df1['generated'].apply(process_hashtags)
df2['HASHTAGS'] = df2['HASHTAGS'].apply(process_hashtags)

# 모든 해시태그를 임베딩하여 사전에 저장
all_hashtags = list(set(tag for tags in df1['generated'] for tag in tags) | set(tag for tags in df2['HASHTAGS'] for tag in tags))

start_time = time.time()
hashtag_embeddings = {tag: embed_text(tag) for tag in all_hashtags}
print(f"Embedding generation took {time.time() - start_time:.2f} seconds.")

# 고유한 열 이름을 보장하기 위해 열 이름에 인덱스를 추가
unique_song_titles = [f"{title}_{i}" for i, title in enumerate(df1['song_title'])]
unique_visit_area_names = [f"{name}_{i}" for i, name in enumerate(df2['VISIT_AREA_NM'])]

# 교차 연산 결과 저장용 데이터 프레임 생성
results_df = pd.DataFrame(index=unique_visit_area_names, columns=unique_song_titles)

# 중간 결과 저장을 위한 파일 경로 설정
json_output_file = 'C:/Users/minjeong/OneDrive/24-2/tripbeats/music/output/standardized_results.json'
csv_output_file = 'C:/Users/minjeong/OneDrive/24-2/tripbeats/music/output/standardized_results.csv'

# 중간 저장 함수 정의
def save_intermediate_results(df, json_path, csv_path, iteration):
    temp_json_path = f"{json_path}_part_{iteration}.json"
    temp_csv_path = f"{csv_path}_part_{iteration}.csv"
    df.to_json(temp_json_path, orient='index', force_ascii=False)
    df.to_csv(temp_csv_path, encoding='utf-8-sig')
    print(f"Intermediate results saved to {temp_json_path} and {temp_csv_path}")

# 각 행별로 교차 연산하여 결과 저장
start_time = time.time()
save_interval = 100  # 100개의 데이터마다 저장
for i, music_index in enumerate(df1.index):
    music_embeddings = np.array([hashtag_embeddings[tag] for tag in df1['generated'][music_index]])
    for j, travel_index in enumerate(df2.index):
        travel_embeddings = np.array([hashtag_embeddings[tag] for tag in df2['HASHTAGS'][travel_index]])
        mean_distance, _ = calculate_mean_distance(music_embeddings, travel_embeddings)
        results_df.at[unique_visit_area_names[travel_index], unique_song_titles[music_index]] = mean_distance

    if (i + 1) % save_interval == 0:
        save_intermediate_results(results_df, json_output_file, csv_output_file, i + 1)

print(f"Similarity calculation took {time.time() - start_time:.2f} seconds.")

# 표준화
scaler = StandardScaler()
standardized_matrix = scaler.fit_transform(results_df.values)

# 표준화된 매트릭스를 데이터프레임으로 변환
standardized_df = pd.DataFrame(standardized_matrix, index=unique_visit_area_names, columns=unique_song_titles)

# 최종 결과 저장
standardized_df.to_json(json_output_file, orient='index', force_ascii=False)
standardized_df.to_csv(csv_output_file, encoding='utf-8-sig')

print(f"Final results saved to {json_output_file} and {csv_output_file}")
