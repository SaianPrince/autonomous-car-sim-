#include <SFML/Graphics.hpp>
#include <SFML/System.hpp>
#include <iostream>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <cmath>
#include <string>

#include "PIDController.h"

#pragma comment(lib, "ws2_32.lib")

const int WINDOW_WIDTH = 800;
const int WINDOW_HEIGHT = 600;

const int ROI_WIDTH = 300;
const int ROI_HEIGHT = 300;

bool sendAll(SOCKET socket, const char* data, int size)
{
    int totalSent = 0;

    while (totalSent < size)
    {
        int sent = send(socket, data + totalSent, size - totalSent, 0);

        if (sent <= 0)
            return false;

        totalSent += sent;
    }

    return true;
}

sf::Image captureRoiFromWindow(sf::RenderWindow& window, sf::RectangleShape& vehicle)
{
    sf::Texture screenTexture;
    screenTexture.create(WINDOW_WIDTH, WINDOW_HEIGHT);
    screenTexture.update(window);

    sf::Image fullImage = screenTexture.copyToImage();

    sf::Image roiImage;
    roiImage.create(ROI_WIDTH, ROI_HEIGHT);

    int roiX = static_cast<int>(vehicle.getPosition().x) - ROI_WIDTH / 2;
    int roiY = static_cast<int>(vehicle.getPosition().y) - 170;

    if (roiX < 0) roiX = 0;
    if (roiY < 0) roiY = 0;
    if (roiX + ROI_WIDTH >= WINDOW_WIDTH) roiX = WINDOW_WIDTH - ROI_WIDTH;
    if (roiY + ROI_HEIGHT >= WINDOW_HEIGHT) roiY = WINDOW_HEIGHT - ROI_HEIGHT;

    for (int y = 0; y < ROI_HEIGHT; y++)
    {
        for (int x = 0; x < ROI_WIDTH; x++)
        {
            sf::Color pixel = fullImage.getPixel(roiX + x, roiY + y);
            roiImage.setPixel(x, y, pixel);
        }
    }

    return roiImage;
}

int main()
{
    sf::RenderWindow window(
        sf::VideoMode(WINDOW_WIDTH, WINDOW_HEIGHT),
        "Autonomous Driving Simulation"
    );

    sf::RectangleShape vehicle(sf::Vector2f(50.f, 80.f));
    vehicle.setFillColor(sf::Color::Blue);
    vehicle.setOrigin(25.f, 40.f);
    vehicle.setPosition(400.f, 520.f);
    vehicle.setRotation(0.f);

    // 3-lane road boundaries
    sf::RectangleShape laneLine1(sf::Vector2f(5.f, 600.f));
    laneLine1.setFillColor(sf::Color::White);
    laneLine1.setPosition(250.f, 0.f);

    sf::RectangleShape laneLine2(sf::Vector2f(5.f, 600.f));
    laneLine2.setFillColor(sf::Color::White);
    laneLine2.setPosition(350.f, 0.f);

    sf::RectangleShape laneLine3(sf::Vector2f(5.f, 600.f));
    laneLine3.setFillColor(sf::Color::White);
    laneLine3.setPosition(450.f, 0.f);

    sf::RectangleShape laneLine4(sf::Vector2f(5.f, 600.f));
    laneLine4.setFillColor(sf::Color::White);
    laneLine4.setPosition(550.f, 0.f);

    // Obstacle in the middle lane
    sf::RectangleShape obstacle(sf::Vector2f(45.f, 45.f));
    obstacle.setFillColor(sf::Color::Red);
    obstacle.setPosition(377.f, 160.f);

    WSADATA wsaData;

    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0)
    {
        std::cout << "WSAStartup failed\n";
        return -1;
    }

    SOCKET clientSocket = socket(AF_INET, SOCK_STREAM, 0);

    if (clientSocket == INVALID_SOCKET)
    {
        std::cout << "Socket creation failed\n";
        WSACleanup();
        return -1;
    }

    sockaddr_in serverAddress;
    serverAddress.sin_family = AF_INET;
    serverAddress.sin_port = htons(5000);

    inet_pton(AF_INET, "127.0.0.1", &serverAddress.sin_addr);

    if (connect(clientSocket, (sockaddr*)&serverAddress, sizeof(serverAddress)) == SOCKET_ERROR)
    {
        std::cout << "Connection failed\n";

        closesocket(clientSocket);
        WSACleanup();

        return -1;
    }

    std::cout << "Connected to Python server\n";

    PIDController steeringPID(0.04f, 0.0f, 0.01f);

    float vehicleSpeed = 70.f;
    float angleError = 0.f;

    sf::Clock clock;

    while (window.isOpen())
    {
        float deltaTime = clock.restart().asSeconds();

        sf::Event event;

        while (window.pollEvent(event))
        {
            if (event.type == sf::Event::Closed)
            {
                window.close();
            }
        }

        window.clear(sf::Color::Black);

        window.draw(laneLine1);
        window.draw(laneLine2);
        window.draw(laneLine3);
        window.draw(laneLine4);

        window.draw(obstacle);
        window.draw(vehicle);

        window.display();

        sf::Image roiImage = captureRoiFromWindow(window, vehicle);

        const sf::Uint8* pixels = roiImage.getPixelsPtr();

        int imageSize = ROI_WIDTH * ROI_HEIGHT * 4;

        bool success = sendAll(
            clientSocket,
            reinterpret_cast<const char*>(pixels),
            imageSize
        );

        if (!success)
        {
            std::cout << "Send failed\n";
            break;
        }

        char commandBuffer[1024] = {};

        int receivedBytes = recv(
            clientSocket,
            commandBuffer,
            sizeof(commandBuffer) - 1,
            0
        );

        if (receivedBytes > 0)
        {
            commandBuffer[receivedBytes] = '\0';

            try
            {
                angleError = std::stof(commandBuffer);

                std::cout
                    << "Angle from Python: "
                    << angleError
                    << std::endl;
            }
            catch (...)
            {
                std::cout << "Invalid command from Python\n";
            }
        }

        float steering = steeringPID.calculate(angleError, deltaTime);

        vehicle.rotate(steering);

        float rotation = vehicle.getRotation() - 90.f;
        float radian = rotation * 3.14159f / 180.f;

        sf::Vector2f direction(
            std::cos(radian),
            std::sin(radian)
        );

        vehicle.move(direction * vehicleSpeed * deltaTime);

        sf::sleep(sf::milliseconds(16));
    }

    closesocket(clientSocket);
    WSACleanup();

    return 0;
}