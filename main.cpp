#include <SFML/Graphics.hpp>
#include <iostream>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <optional>

#pragma comment(lib,"ws2_32.lib")

int main()
{
    // SFML 3.0 uses sf::Vector2u for VideoMode
    sf::RenderWindow window(
        sf::VideoMode({800, 600}),
        "Autonomous Driving Simulation"
    );

    // Vehicle
    sf::RectangleShape vehicle(
        sf::Vector2f({50.f, 80.f})
    );

    vehicle.setFillColor(sf::Color::Red);
    vehicle.setPosition({375.f, 450.f});

    // Lane markers
    sf::RectangleShape leftLane(
        sf::Vector2f({5.f, 600.f})
    );

    leftLane.setPosition({300.f, 0.f});
    leftLane.setFillColor(sf::Color::White);


    sf::RectangleShape rightLane(
        sf::Vector2f({5.f, 600.f})
    );

    rightLane.setPosition({500.f, 0.f});
    rightLane.setFillColor(sf::Color::White);


    // Initialize Winsock
    WSADATA wsaData;
    WSAStartup(
        MAKEWORD(2, 2),
        &wsaData
    );

    // Create TCP socket
    SOCKET clientSocket =
        socket(
            AF_INET,
            SOCK_STREAM,
            0
        );

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
        return -1;
    }

    std::cout << "Connected to Python server\n";


    while (window.isOpen())
    {
        // SFML 3.0 new event system
        while (const std::optional event = window.pollEvent())
        {
            if (event->is<sf::Event::Closed>())
                window.close();
        }


        // Send one frame signal
        const char* frameMessage = "FRAME\n";

        send(
            clientSocket,
            frameMessage,
            (int)strlen(frameMessage),
            0
        );


        // Receive command
        char commandBuffer[1024] = {};

        int receivedBytes =
            recv(
                clientSocket,
                commandBuffer,
                sizeof(commandBuffer) - 1,
                0
            );

        if (receivedBytes > 0)
        {
            std::cout
                << "Received command: "
                << commandBuffer
                << std::endl;
        }


        window.clear();

        window.draw(leftLane);
        window.draw(rightLane);
        window.draw(vehicle);

        window.display();
    }


    closesocket(clientSocket);
    WSACleanup();

    return 0;
}
