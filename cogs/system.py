import os
import json

import aiohttp
import pathlib
import asyncio
import signal

from typing import List

import discord
from discord.ext import commands
from discord import app_commands

MODEL_DB = pathlib.Path("database/models.json")
MODEL_DIR = pathlib.Path("models")

LLAMA_SERVER = pathlib.Path("/home/baihu/llama.cpp/build/bin/llama-server")

async def model_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    cog = interaction.client.get_cog("LLMController")
    models = getattr(cog, "models", {})

    return [
        app_commands.Choice(name = model_name, value = model_name)
        for model_name in models.keys()
        if current.lower() in model_name.lower()
    ][:25]

class LLMController(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.models = self._load_models()

        self.model_process = None
        self.current_model = None

    def _load_models(self) -> dict:
        if not MODEL_DB.exists(): return {}

        try:
            with MODEL_DB.open("r", encoding = "utf-8") as f:
                return json.load(f)

        except json.JSONDecodeError:
            return {}

    def _save_models(self):
        MODEL_DB.parent.mkdir(parents = True, exist_ok = True)

        with MODEL_DB.open("w", encoding = "utf-8") as f: json.dump(self.models, f, indent = 4)

    def _write_chunk(self, file_obj, chunk):
        file_obj.write(chunk)

    @app_commands.command(name = "add_model", description = "Add a new LLM GGUF model")
    async def add_model(self, interaction: discord.Interaction, name: str, model_url: str):
        await interaction.response.defer()

        MODEL_DIR.mkdir(parents = True, exist_ok = True)
        model_path = MODEL_DIR / f"{name}.gguf"

        if model_path.exists():
            return await interaction.followup.send(
                discord.Embed(
                    title = "Model Already Exists",
                    description = f"A model named '**{name}**' already exists. Please choose a different name.",
                    color = discord.Color.red()
                )
            )
        
        def make_progress_bar(percentage: float) -> str:
            total_blocks = 20

            filled_blocks = int(percentage // (100 / total_blocks))
            empty_blocks = total_blocks - filled_blocks

            return f"`{'▬' * filled_blocks}{'○' * empty_blocks}` `{percentage:.2f}%`"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(model_url) as response:
                    if response.status != 200:
                        return await interaction.followup.send(
                            embed = discord.Embed(
                                title = "Download Failed",
                                description = f"Failed to download model from the provided URL. Status code: {response.status}",
                                color = discord.Color.red()
                            )
                        )

                    total_size = int(response.headers.get("Content-Length", 0))

                    downloaded_size = 0.0
                    last_update_time = 0.0

                    with open(model_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(1024 * 1024):
                            await asyncio.to_thread(self._write_chunk, f, chunk)
                            downloaded_size += len(chunk)

                            if total_size > 0:
                                percent = (downloaded_size / total_size) * 100
                                current_time = asyncio.get_event_loop().time()

                                if current_time - last_update_time > 3 or downloaded_size == total_size:
                                    progress_bar = make_progress_bar(percent)
                                    try:
                                        await interaction.followup.edit_message(
                                            message_id = "@original", 
                                            embed = discord.Embed(
                                                title = f"Downloading '{name}'",
                                                description = f"{progress_bar}\n`{downloaded_size / (1024 * 1024 * 1024):.2f} GB / {total_size / (1024 * 1024 * 1024):.2f} GB`",
                                                color = discord.Color.blue()
                                            )
                                        )
                                    except discord.HTTPException: pass

                                    last_update_time = current_time

            self.models[name] = str(model_path)
            self._save_models()

            file_size = model_path.stat().st_size / (1024 * 1024 * 1024)

            await interaction.followup.edit_message(
                message_id = "@original",
                embed = discord.Embed(
                    title = f"Model '{name}' added successfully!",
                    description = f"Size: {file_size:.2f} GB",
                    color = discord.Color.green()
                )
            )

        except Exception as e:
            await interaction.followup.send(
                embed = discord.Embed(
                    title = "Download Failed",
                    description = f"An error occurred while downloading the model: {e}",
                    color = discord.Color.red()
                )
            )

    @app_commands.command(name = "remove_model", description = "Remove an existing LLM GGUF model")
    @app_commands.autocomplete(model = model_autocomplete)
    async def remove_model(self, interaction: discord.Interaction, model: str):
        await interaction.response.defer()

        path = self.models.get(model)

        if not path: 
            return await interaction.followup.send(
                embed = discord.Embed(
                    title = "Model Not Found",
                    description = f"Model '{model}' not found.",
                    color = discord.Color.red()
                )
            )

        if self.current_model == model:
            return await interaction.followup.send(
                embed = discord.Embed(
                    title = "Cannot Remove Model",
                    description = f"Cannot remove model '{model}' while it is running. Please stop it first.",
                    color = discord.Color.red()
                )
            )

        try: os.remove(path)
        except FileNotFoundError: pass

        del self.models[model]
        self._save_models()

        await interaction.followup.send(
            embed = discord.Embed(
                title = "Model Removed",
                description = f"Model '{model}' removed successfully.",
                color = discord.Color.green()
            )
        )
    
    @app_commands.command(name = "models_list", description = "List all available LLM GGUF models")
    async def models_list(self, interaction: discord.Interaction):
        if not self.models:
            return await interaction.response.send_message(
                embed = discord.Embed(
                    title = "No Models Available",
                    description = "No models available. Use /add_model to add one.",
                    color = discord.Color.red()
                )
            )

        model_list = "\n".join(
            f"- {name} ({'Running' if name == self.current_model else 'Stopped'})"
            for name in self.models.keys()
        )

        await interaction.response.send_message(
            embed = discord.Embed(
                title = "Available LLM Models",
                description = model_list,
                color = discord.Color.blue()
            )
        )
    
    @app_commands.command(name = "start_model", description = "Start the LLM server with a specified model")
    @app_commands.autocomplete(model = model_autocomplete)
    async def start_model(self, interaction: discord.Interaction, model: str, ngl: int = 30, ctx: int = 4096):
        if self.model_process and self.model_process.returncode is None:
            return await interaction.response.send_message(
                embed = discord.Embed(
                    title = "Model Already Running",
                    description = f"Model '{self.current_model}' is already running. Please stop it first.",
                    color = discord.Color.red()
                )
            )

        path = self.models.get(model)
        if not path:
            return await interaction.response.send_message(
                embed = discord.Embed(
                    title = "Model Not Found",
                    description = f"Model '{model}' not found.",
                    color = discord.Color.red()
                )
            )

        if not LLAMA_SERVER.exists():
            return await interaction.response.send_message(
                embed = discord.Embed(
                    title = "Server Not Found",
                    description = "LLaMA server executable not found. Please check the path.",
                    color = discord.Color.red()
                )
            )

        await interaction.response.defer()

        self.model_process = await asyncio.create_subprocess_exec(
            str(LLAMA_SERVER), "-m", path, "--host", "0.0.0.0", "--port", "8000", "-ngl", str(ngl), "-c", str(ctx),
            stdout = asyncio.subprocess.DEVNULL, stderr = asyncio.subprocess.DEVNULL
        )

        self.current_model = model

        await interaction.followup.send(
            embed = discord.Embed(
                title = "Model Started",
                description = f"Model '{model}' started successfully on port 8000!",
                color = discord.Color.green()
            )
        )

    @app_commands.command(name = "stop_model", description = "Stop the currently running LLM server")
    async def stop_model(self, interaction: discord.Interaction):
        if not self.model_process or self.model_process.returncode is not None:
            return await interaction.response.send_message(
                embed = discord.Embed(
                    title = "No Model Running",
                    description = "No model is currently running.",
                    color = discord.Color.red()
                )
            )

        self.model_process.send_signal(signal.SIGINT)
        await self.model_process.wait()

        stopped_model = self.current_model

        self.model_process = None
        self.current_model = None

        await interaction.response.send_message(
            embed = discord.Embed(
                title = "Model Stopped",
                description = f"Model '{stopped_model}' stopped successfully.",
                color = discord.Color.green()
            )
        )

async def setup(bot):
    await bot.add_cog(LLMController(bot))