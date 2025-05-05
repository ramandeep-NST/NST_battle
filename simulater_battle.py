import subprocess
import random
import os
import itertools
import timeit
from pymongo import MongoClient, errors
import certifi
import tempfile
from multiprocessing import Pool, cpu_count

R = 5
N = 5
numberOfStudents = 0
nameToScore = {}
emailToName = {}
indexToEmail = [""] * 410
timesOfSubmission = [""] * 410
indexToName = [""] * 410
strategies = [""] * 410
base_dir = os.path.dirname(os.path.abspath(__file__))

mongo_uri = "mongodb+srv://gautam:CramersRule_24@cluster0.x7sgg65.mongodb.net/DSA-Open-Book-LeaderBoard?retryWrites=true&w=majority&appName=Cluster0"
db_name = "DSA-Open-Book-LeaderBoard"
collection_name = "users"


def connect_to_mongo(mongo_uri, db_name, collection_name):
    client = MongoClient(mongo_uri, tlsCAFile=certifi.where())
    db = client[db_name]
    return db[collection_name]


def save_script_to_temp_file(script_content):
    with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.py') as temp_file:
        temp_file.write(script_content)
        return temp_file.name


def load_strategies_from_mongodb():
    collection = connect_to_mongo(mongo_uri, db_name, collection_name)
    global numberOfStudents
    numberOfStudents = collection.count_documents({})
    print(f"Found {numberOfStudents} strategies in Database")

    index = 0
    for doc in collection.find():
        strategy_name = doc.get('email')
        code_content = doc.get('code')
        name = doc.get('name')
        timeStamp = doc.get('submittedAt')
        nameToScore[strategy_name] = name
        indexToEmail[index] = strategy_name
        indexToName[index] = name
        timesOfSubmission[index] = timeStamp
        if code_content:
            strategies[index] = save_script_to_temp_file(code_content)
        else:
            print(f"Empty or invalid code for: {strategy_name}")
        index += 1
    return timesOfSubmission


def update_score_in_mongodb(mongo_uri, db_name, collection_name, strategy_name, score, rank):
    collection = connect_to_mongo(mongo_uri, db_name, collection_name)
    try:
        result = collection.update_one(
            {"email": strategy_name},
            {"$set": {"score": score, "rank": rank}}
        )
        if result.matched_count == 0:
            print(f"⚠️ No entry found for {strategy_name} in DB.")
    except errors.PyMongoError as e:
        print(f"Mongo error for {strategy_name}: {e}")


def start_persistent_strategy(strategy_file, N, E):
    process = subprocess.Popen(
        ['python3', strategy_file],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )
    try:
        process.stdin.write(f"{N}\n{E}\n")
        process.stdin.flush()
        _ = process.stdout.readline()
        return process
    except Exception as e:
        print(f"Failed to start strategy {strategy_file}: {e}")
        process.kill()
        return None


def interact_with_strategy(process, opponent_bids, E):
    try:
        if process.poll() is not None:
            raise BrokenPipeError("Strategy process has exited unexpectedly.")

        process.stdin.write(" ".join(map(str, opponent_bids)) + "\n")
        process.stdin.write(f"{E}\n")
        process.stdin.flush()

        line = process.stdout.readline().strip()


        err = process.stderr.readline().strip()
        if err:
            print(f"⚠️ Strategy stderr: {err}")

        if not line:
            return [0] * len(opponent_bids)

        cleaned = line.replace('[', '').replace(']', '').replace(',', ' ')
        bid = list(map(int, cleaned.split()))
        return bid if len(bid) == len(opponent_bids) else [0] * len(opponent_bids)

    except Exception as e:
        print(f"Error interacting with strategy: {e}")
        return [0] * len(opponent_bids)



def terminate_strategy(process):
    try:
        process.stdin.write("0 0 0 0 0\n-1\n")
        process.stdin.flush()
        process.terminate()
    except Exception:
        pass


def calculate_score(bid1, bid2, N):
    res1 = res2 = 0
    score1 = score2 = 0
    for a, b in zip(bid1, bid2):
        if a > b:
            score1 += 3
            res1 += 1
        elif b > a:
            score2 += 3
            res2 += 1
        else:
            score1 += 1
            score2 += 1
    if res1 > res2:
        score1 += 3 * N
    elif res2 > res1:
        score2 += 3 * N
    else:
        score1 += N
        score2 += N
    return score1, score2

def simulate_match(args):
    team1, team2, team_files, R = args
    E_list = [random.randint(100, 500) for _ in range(R)]
    total_scores = {team1: 0, team2: 0}
    previous_bids = {team1: [0] * N, team2: [0] * N}
    round_bids = {}

    proc1 = start_persistent_strategy(team_files[team1], N, E_list[0])
    proc2 = start_persistent_strategy(team_files[team2], N, E_list[0])

    if not proc1 or not proc2:
        print(f"[Match Skipped] {team1} vs {team2} — Could not start one or both strategies.")
        return (team1, team2, 0, 0)

    for round_num in range(R):
        E = E_list[round_num]

        bid1 = interact_with_strategy(proc1, previous_bids[team2], E)
        bid2 = interact_with_strategy(proc2, previous_bids[team1], E)

        round_bids[team1] = bid1
        round_bids[team2] = bid2

        s1, s2 = calculate_score(bid1, bid2, N)
        total_scores[team1] += s1
        total_scores[team2] += s2
        previous_bids[team1] = bid1
        previous_bids[team2] = bid2

    terminate_strategy(proc1)
    terminate_strategy(proc2)

    print(f"[Match Result] {team1} vs {team2} → {total_scores[team1]} : {total_scores[team2]}")
    return (team1, team2, total_scores[team1], total_scores[team2])


if __name__ == "__main__":
    timesOfSubmission = load_strategies_from_mongodb()
    teams = []
    team_files = {}
    scores = {}
    start = timeit.default_timer()

    for i, strategy_path in enumerate(strategies):
        if strategy_path:
            team_name = f"Team {i + 1} - {indexToName[i]}"
            teams.append(team_name)
            team_files[team_name] = strategy_path
            scores[team_name] = 0

    match_args = [(team1, team2, team_files, R) for team1, team2 in itertools.combinations(teams, 2)]
    print(f"\nRunning {len(match_args)} matches using {cpu_count()} CPU cores...\n")

    with Pool(processes=cpu_count()) as pool:
        results = pool.map(simulate_match, match_args)

    for team1, team2, score1, score2 in results:
        scores[team1] += score1
        scores[team2] += score2

    end = timeit.default_timer()
    print(f"\n⏱ Total Time Taken: {end - start:.2f} seconds")

    print("\n=== Final Standings ===")
    team_data = []
    for team in teams:
        score = scores[team]
        index = teams.index(team)
        timestamp = timesOfSubmission[index]
        team_data.append((team, score, timestamp))

    ranked_teams = sorted(team_data, key=lambda x: (-x[1], x[2] if x[2] else "9999-12-31T23:59:59"))

    for rank, (team, score, timestamp) in enumerate(ranked_teams, 1):
        print(f"{rank}. {team} - {score} points")
        team_index = teams.index(team)
        email = indexToEmail[team_index]
        # update_score_in_mongodb(mongo_uri, db_name, collection_name, email, score, rank)

    print(f"\n🏆 Tournament Winner: {ranked_teams[0][0]} with {ranked_teams[0][1]} points 🏆")
