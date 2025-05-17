import discord

LOGO = "https://i.imgur.com/fjIYhig.png"

class Paginator(discord.ui.View):
    def __init__(self) -> None:
      super().__init__(timeout=900)
      self.data : list # Expecting this to be assiged after instantiation
      self.title : str # Expecting this to be assiged after instantiation
      self.sep = 5 # Expecting this to be assiged after instantiation
      self.current_page = 1 # LEAVE AS 1
      self.category : discord.Category = None # Optional
      self.count : bool = False # Optional

    async def send(self, interaction: discord.Interaction):
      try:
        await interaction.response.send_message(view=self, content="")
      except:
        await interaction.edit_original_response(view=self, content="")
      await self.update_message(interaction)

    def create_embed(self):
      embed = discord.Embed(title=self.title, description="",  color=discord.Color.gold())
      footer_text = self.get_footer_text()
      if self.data[0] == "No data found.":
        embed.description = "No data found."
      else:
        if self.count:
          for index, item in enumerate(self.get_current_page_data()):
            embed.description += f"**{(self.sep*self.current_page)-(self.sep-(index+1))}.** {item}\n"
        else:
          for item in self.get_current_page_data():
            embed.description += f"{item}\n"
      if footer_text:
        embed.set_footer(icon_url=LOGO, text=footer_text)
      return embed

    async def update_message(self, interaction: discord.Interaction):
      self.update_buttons()
      await interaction.edit_original_response(embed=self.create_embed(), view=self)

    def update_buttons(self):
      if self.data[0] == "No data found.":
        return
      total_pages = (int(len(self.data) / self.sep))
      total_pages += 1 if int(len(self.data)) % self.sep != 0 else 0
      is_first_page = self.current_page == 1
      is_last_page = self.current_page == total_pages
      self.first_page_button.disabled = is_first_page
      self.prev_button.disabled = is_first_page
      self.first_page_button.style = discord.ButtonStyle.gray if is_first_page else discord.ButtonStyle.red
      self.prev_button.style = discord.ButtonStyle.gray if is_first_page else discord.ButtonStyle.red
      self.next_button.disabled = is_last_page
      self.last_page_button.disabled = is_last_page
      self.last_page_button.style = discord.ButtonStyle.gray if is_last_page else discord.ButtonStyle.red
      self.next_button.style = discord.ButtonStyle.gray if is_last_page else discord.ButtonStyle.red

    def get_current_page_data(self):
      until_item = self.current_page * self.sep
      from_item = until_item - self.sep if self.current_page != 1 else 0
      return self.data[from_item:until_item]

    def get_footer_text(self):
      total_pages = (int(len(self.data) / self.sep))
      total_pages += 1 if int(len(self.data)) % self.sep != 0 else 0
      return f"Page {self.current_page}/{total_pages} ({len(self.data)} total) | Minecadia Support Bot"

    async def handle_page_button(self, interaction: discord.Interaction, step: int):
      await interaction.response.defer()
      self.current_page += step
      await self.update_message(interaction)

    @discord.ui.button(label="|<", style=discord.ButtonStyle.gray, disabled=True, custom_id="lskip")
    async def first_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
      await self.handle_page_button(interaction, 1 - self.current_page)

    @discord.ui.button(label="<", style=discord.ButtonStyle.gray, disabled=True, custom_id="left")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
      await self.handle_page_button(interaction, -1)

    @discord.ui.button(label=">", style=discord.ButtonStyle.gray, disabled=True, custom_id="right")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
      await self.handle_page_button(interaction, 1)

    @discord.ui.button(label=">|", style=discord.ButtonStyle.gray, disabled=True, custom_id="rskip")
    async def last_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
      total_pages = (int(len(self.data) / self.sep))
      total_pages += 1 if int(len(self.data)) % self.sep != 0 else 0
      await self.handle_page_button(interaction, total_pages - self.current_page)