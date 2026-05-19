import os, discord, traceback
from discord.ext import commands

class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()

        super().__init__(
            command_prefix = "♡",
            intents = intents
        )
        
    async def setup_hook(self):
        await self.load_extensions()
        await self.tree.sync()
           
    async def load_extensions(self):
        for root, _, files in os.walk("./cogs"):
            for file in files:
                if file.endswith(".py"):
                    rel_path = os.path.relpath(os.path.join(root, file), ".")
                    extension = rel_path.replace(os.sep, ".")[:-3]
                    
                    try: await super().load_extension(extension)
                    except Exception as e: 
                        print(f"[LOAD FAIL] {extension}")
                        traceback.print_exc()
    
    async def on_ready(self): pass
    async def close(self): await super().close()