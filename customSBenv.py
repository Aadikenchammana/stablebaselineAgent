import gymnasium as gym
import numpy as np
from gymnasium import spaces
import simfire
from simfire.enums import GameStatus, BurnStatus
from stable_baselines3.common.env_checker import check_env
from stable_baselines3.common.callbacks import BaseCallback
from numpy import zeros,newaxis
import time
import random
import os
from datetime import datetime
import math

def save_array_to_file(array, filename):

    # Convert array to string with custom format
    array_str = '|'.join(','.join(str(cell) for cell in row) for row in array)
    # Save string to file
    with open(filename, 'w') as file:
        file.write(array_str)
    

def get_burning(mp):
    count = 0
    for row in mp:
        for item in row:
            if item == 1:
                count +=1
    return count

def get_burned(mp):
    count = 0
    for row in mp:
        for item in row:
            if item == 2:
                count +=1
    return count

def get_unburned(mp):
    count = 0
    for row in mp:
        for item in row:
            if item == 0:
                count +=1
    return count    

def get_mitigated(mp):
    count = 0
    for row in mp:
        for item in row:
            if item == 3:
                count +=1
    return count 

def get_total(mp):
    burning = get_burning(mp)
    burned = get_burned(mp)
    unburned = get_unburned(mp)
    return burned+burning+unburned

def get_reward(mp):
    burning = get_burning(mp)
    burned = get_burned(mp)
    unburned = get_unburned(mp)

    return -10*(burning+burned)/(burning+burned+unburned)

def get_reward_l2(mp, x, y):
    dist, square = distance_to_fire(mp,x,y)
    dist -= 2

    return -10*(get_burning(mp)+get_burned(mp))/get_total(mp) - 0.5*dist - 0.1*get_mitigated()

def run_one_simulation_step(self, total_updates):
    num_updates = 0

    while self.sim.fire_status == GameStatus.RUNNING and num_updates < total_updates:
        self.sim.fire_sprites = self.sim.fire_manager.sprites
        self.sim.fire_map, self.sim.fire_status = self.sim.fire_manager.update(self.sim.fire_map)
        if self.sim._rendering:
            self.sim._render()
        num_updates += 1

        self.sim.elapsed_steps += 1
        
        if self.sim.config.simulation.save_data:
            self.sim._save_data()

    self.sim.active = True if self.sim.fire_status == GameStatus.RUNNING else False
    return self.sim.fire_map, self.sim.active

def calc_random_start(screen_size):
    return(random.randint(0,screen_size-1),random.randint(0,screen_size-1))

def distance_to_fire(mp,x,y):
    i = -1
    mn = 2*int(mp.shape[1])
    closest_square = []
    flag = True
    for row in mp:
        i+=1
        j = -1
        for item in row:
            j+=1
            if item == 1 and np.sqrt((x-i)**2+(y-j)**2) < mn:
                flag = False
                mn = np.sqrt((x-i)**2+(y-j)**2)
                closest_square = [i,j]
    if flag:
        return 0,[0,0]
    return mn, closest_square

def square_state(mp, x, y):
    return mp[y][x]

class SaveModelCallback(BaseCallback):
    """
    A custom callback that saves the model.
    """
    def __init__(self, save_path, check_freq, verbose=1):
        super(SaveModelCallback, self).__init__(verbose)
        self.save_path = save_path
        self.check_freq = check_freq

    def _on_step(self) -> bool:
        if self.n_calls % self.check_freq == 0:
            self.model.save(os.path.join(self.save_path, f'model_{self.num_timesteps}'))

class CustomEnv(gym.Env):
    """Custom Environment that follows gym interface."""

    metadata = {"render_modes": ["human"], "render_fps": 30}

    def __init__(self):
        super().__init__()

        self.config = simfire.utils.config.Config("configs/operational_config.yml")
        print(self.config.area.screen_size)
        print(self.config)
        self.config.fire.fire_initial_position = calc_random_start(self.config.area.screen_size[0])
        print(self.config.fire.fire_initial_position)
        
        self.sim = simfire.sim.simulation.FireSimulation(self.config)
        self.screen_size = self.config.area.screen_size[0]
        self.agent_x = 10
        self.agent_y = 10
        self.agent_start = [10,10]
        self.episode_steps = 0
        self.updates_per_step = 1
        self.total_steps_per_episode = 1200
        self.episodes_per_fire_restart = 2500
        self.chkpt_thresh = 100
        self.simulation_steps_per_timestep = 8
        self.episode_num = 0
        self.autoplace = True

        self.analytics_dir = "train_analytics//"+datetime.now().strftime("%m.%d.%Y_%H:%M:%S")
        if os.path.isdir(self.analytics_dir) == False:
            os.mkdir(self.analytics_dir)
            os.mkdir(self.analytics_dir+"//fires")
        with open(self.analytics_dir+"//customLog.txt","w") as f:
            f.write("")
        with open(self.analytics_dir+"//rewardLog.txt","w") as f:
            f.write("")

        with open(self.analytics_dir+"//customLog.txt","w") as f:
            f.write("\nENVIRONMENT GENERATED")

        self.chkpt_flag = True
        self.chkpt_dir = self.analytics_dir+"//fires//0"
        os.mkdir(self.chkpt_dir)

        
        if self.autoplace:
            n_actions = 4
            self.action_space = spaces.Discrete(n_actions)
            self.action_names = ["up","down","left","right"]
        else:
            n_actions = 5
            self.action_space = spaces.Discrete(n_actions)
            self.action_names = ["up","down","left","right","fireline"]
        n_channel = 1
        self.observation_space = spaces.Box(low=0, high=255,shape=(n_channel, self.screen_size, self.screen_size), dtype=np.int64)


    def step(self, action):
        self.episode_steps += 1
        action_str = self.action_names[action]
        action_multiplier = 1

        with open(self.analytics_dir+"//customLog.txt","a") as f:
            f.write("\n ACTION PREFORMED, "+action_str+","+str(self.agent_x)+","+str(self.agent_y))
        if action_str == "up":
            self.agent_y -= 1*action_multiplier
        elif action_str == "down":
            self.agent_y += 1*action_multiplier
        elif action_str == "left":
            self.agent_x -= 1*action_multiplier
        elif action_str == "right":
            self.agent_x +=1*action_multiplier
        
        if self.agent_x > self.screen_size-1:
            self.agent_x = self.screen_size-1 #self.agent_start[0]
        if self.agent_y > self.screen_size-1:
            self.agent_y = self.screen_size-1 #self.agent_start[1]
        if self.agent_x < 0:
            self.agent_x = 0 #self.agent_start[0]
        if self.agent_y < 0:
            self.agent_y = 0 #self.agent_start[1]
        
        if action_str == "fireline":
            self.sim.update_mitigation([(self.agent_x,self.agent_y,BurnStatus.FIRELINE)])
        
        if self.autoplace:
            self.sim.update_mitigation([(self.agent_x,self.agent_y,BurnStatus.FIRELINE)])

        if self.episode_steps%self.simulation_steps_per_timestep == 0:
            self.fire_map, self.fire_status = run_one_simulation_step(self, self.updates_per_step)


        self.observation = self.fire_map[newaxis,:,:]
        terminated = False
        truncated = False
        if self.episode_steps > self.total_steps_per_episode:
            terminated = True
        if get_burning(self.fire_map) == 0:
            terminated = True
            truncated = False
        reward = get_reward_l2(self.fire_map, self.agent_x, self.agent_y)#get_reward(self.fire_map)
        if square_state(self.fire_map, self.agent_x,self.agent_y) == 1:
            reward -= 10

        with open(self.analytics_dir+"//customLog.txt","a") as f:
            f.write("\n REWARD CALCULATED, "+str(reward)+","+str(get_burned(self.fire_map))+","+str(get_burning(self.fire_map))+","+str(get_unburned(self.fire_map)))
        
        with open(self.analytics_dir+"//rewardLog.txt","a") as f:
            f.write("\n REWARD, "+str(reward)+","+str(get_burned(self.fire_map))+","+str(get_burning(self.fire_map))+","+str(get_unburned(self.fire_map))+","+str(distance_to_fire(self.fire_map,self.agent_x,self.agent_y)[0]))

        if self.chkpt_flag:
            #save_array_to_file(self.fire_map, self.chkpt_dir+"//"+str(self.episode_steps)+".txt")
            np.save(self.chkpt_dir+"//"+str(self.episode_steps)+".npy",self.fire_map)
        
        info = {}
        return self.observation, reward, terminated, truncated, info

    def reset(self, seed=None, options=None):
        super().reset(seed=seed, options=options)
        self.episode_num +=1
        if self.episode_num % self.chkpt_thresh == 0:
            self.chkpt_flag = True
            self.chkpt_dir = self.analytics_dir+"//fires//"+str(self.episode_num)
            os.mkdir(self.chkpt_dir)
        if self.episode_num%self.episodes_per_fire_restart == 0:
            self.config.fire.fire_initial_position = calc_random_start(self.config.area.screen_size[0])
        self.sim = simfire.sim.simulation.FireSimulation(self.config)
        self.sim.reset()
        self.fire_map, self.fire_status = run_one_simulation_step(self, 1)
        self.observation_return = self.fire_map[newaxis,:,:]
        self.episode_steps = 0
        self.agent_x = self.agent_start[0]
        self.agent_y = self.agent_start[1]

        with open(self.analytics_dir+"//customLog.txt","a") as f:
            f.write("\n NEW TRAINING ITERATION CREATION")
        with open(self.analytics_dir+"//rewardLog.txt","a") as f:
            f.write("\n NEW TRAINING ITERATION CREATION")

        info = {}
        return self.observation_return, info



    def render(self):
        ...

    def close(self):
        ...


from stable_baselines3 import DQN, PPO
from stable_baselines3.common.evaluation import evaluate_policy
env = CustomEnv()
if False:
    check_env(env)
    quit()
# Instantiate the agent
#model = DQN("MlpPolicy", env, verbose=1)
model = PPO('MlpPolicy', env, verbose=1)
save_path = 'saved_models//'+datetime.now().strftime("%m.%d.%Y_%H:%M:%S")
os.mkdir(save_path)
save_path += "//"
callback = SaveModelCallback(save_path=save_path, check_freq=10000)
# Train the agent and display a progress bar
model.learn(total_timesteps=int(8e6), progress_bar=True, callback=callback)
# Save the agent
model.save("dqn_lunar")
del model