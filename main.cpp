#include <SFML/Graphics.hpp>
#include <SFML/System.hpp>
#include <iostream>
#include <winsock2.h>
#include <ws2tcpip.h>

#pragma comment(lib, "ws2_32.lib")

const int WINDOW_WIDTH = 800;
const int WINDOW_HEIGHT = 600;
const int ROI_WIDTH = 200;
const int ROI_HEIGHT = 200;

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

sf::Image captureRoiFromWindow(sf::RenderWindow& window)
{
    sf::Texture screenTexture;
    screenTexture.create(WINDOW_WIDTH, WINDOW_HEIGHT);
    screenTexture.update(window);

    sf::Image fullImage = screenTexture.copyToImage();

    sf::Image roiImage;
    roiImage.create(ROI_WIDTH, ROI_HEIGHT);

    int roiX = 300;
    int roiY = 250;

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
    vehicle.setFillColor(sf::Color::Red);
    vehicle.setPosition(375.f, 450.f);

    sf::RectangleShape leftLane(sf::Vector2f(5.f, 600.f));
    leftLane.setFillColor(sf::Color::White);
    leftLane.setPosition(300.f, 0.f);

    sf::RectangleShape rightLane(sf::Vector2f(5.f, 600.f));
    rightLane.setFillColor(sf::Color::White);
    rightLane.setPosition(500.f, 0.f);

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

    inet_pton(
        AF_INET,
        "127.0.0.1",
        &serverAddress.sin_addr
    );

    if (connect(
        clientSocket,
        (sockaddr*)&serverAddress,
        sizeof(serverAddress)
    ) == SOCKET_ERROR)
    {
        std::cout << "Connection failed\n";

        closesocket(clientSocket);
        WSACleanup();

        return -1;
    }

    std::cout << "Connected to Python server\n";

    while (window.isOpen())
    {
        sf::Event event;

        while (window.pollEvent(event))
        {
            if (event.type == sf::Event::Closed)
            {
                window.close();
            }
        }

        window.clear(sf::Color::Black);

        window.draw(leftLane);
        window.draw(rightLane);
        window.draw(vehicle);

        window.display();

        sf::Image roiImage = captureRoiFromWindow(window);

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

        std::cout << "Frame sent\n";

        sf::sleep(sf::milliseconds(16));
    }

    closesocket(clientSocket);
    WSACleanup();

    return 0;
}