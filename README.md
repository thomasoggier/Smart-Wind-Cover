# Smart-Wind-Cover
Smart Wind Cover







Start docker

docker run -d `
  --name ha-dev `
  -p 8123:8123 `
  -v "${PWD}\custom_components\smart_wind_cover:/config/custom_components/smart_wind_cover" `
  ghcr.io/home-assistant/home-assistant:stable

  