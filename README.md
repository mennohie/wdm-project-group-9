# Web-scale Data Management Project Team 9


NOTE TO REVIEWERS


The transactions that are processed by RabbitMQ are demonstrably eventually consistent (if executed on 1 queue). However, with the current implementation, the [benchmark](https://github.com/delftdata/wdm-project-benchmark) that is provided will not agree as the evaluation starts before RabbitMQ can finish processing all messages.


Inserting a sleep statement of ~10 seconds before the evaluation step will ensure the database ends up being consistent. The logs do not give proper results based on our current implementation.


### Running the code
- Copy `.env.example` and rename it to `.env`. Change environment to your liking.
- Run ```python generate_compose.py``` to create the docker-compose file based on the amount of consumers needed, which can be defined in ```.env```.
- To then start the cluster, you can run: ```docker-compose -f docker-compose.yml -f consumer-compose.yml up```.


### Design decisions
In this README we give an overview of our biggest design decision with more elaborate explanations in the wiki.
- We chose to use RabbitMQ as our message broker [Message broker](https://github.com/mennohie/wdm24-team9/wiki/Concept-Message-Broker). Due to using this message broker, we make the system more scalable using asynchronous communication.
- The consumers in this system can be scaled horizontally. This means that we can add more consumers to the system to handle more messages. This is done by running multiple instances of the consumer.
- We use [SAGAs](https://github.com/mennohie/wdm24-team9/wiki/Concept-SAGAS) to handle the transactions in the system. This allows us to combine the information from multiple services (payment and stock) to create a consistent state in the system. Publisher try to process the order step by step, if one step fails the publisher will send a message to rollback the previous steps.
#### Sharding
We have chosen to shard the checkout queues based on user ID, this means that all calls from a certain user get assigned to the same queue. This assures that the order of the call is maintained. For example, if a user tries to buy a product and then tries to buy another product, the order of these calls is maintained.
#### Downside
Due to our asynchronous communication, the system can become inconsistent if multiple users are trying to buy the same product at the same time. In the method `subtract_stock` of the Stock Service, the new stock is calculated in memory and then updated to the database. If this calculation happens with a value that is outdated, this will create an inconsistency.  As we want to be able to scale the system horizontally, we can't use a lock to prevent this from happening. In a real-life scenario, we would send an e-mail to clients and refund their money. We expect this to happen rarely in a real-life scenario, as two users would have to buy the same product within milliseconds of each other.
#### Fault Tolerance
For Fault Tolerance we use persistent queues and dbs to ensure that messages are not lost. If a consumer fails, the message will be requeued and be processed once the queue is available again. This ensures that no messages are lost in the system.