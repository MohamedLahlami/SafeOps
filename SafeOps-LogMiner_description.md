# **Product Requirement Document (PRD): SafeOps-LogMiner**

## **1\. Executive Summary**

**SafeOps-LogMiner** is a microservices-based DevSecOps platform designed to detect security anomalies in CI/CD pipelines. This project serves as a joint academic capstone for microservices and machine learning curricula. The system ingest build logs from CI/CD providers (GitHub Actions, GitLab CI), parses them into structured data, and utilizes an unsupervised machine learning model (**Isolation Forest**) to flag anomalous behaviors such as cryptomining, data exfiltration, and erratic build executions.

The system is explicitly architected to operate within mid-range hardware constraints (Intel i5, 16GB RAM, GTX 1650\) by prioritizing computationally efficient algorithms over resource-heavy Large Language Models (LLMs).1

## **2\. Problem Statement**

Modern CI/CD pipelines are high-velocity environments where security breaches often go undetected. Traditional static analysis tools (SAST) catch code vulnerabilities but fail to detect *runtime anomalies*, such as:

* A build taking 300% longer than usual (potential cryptomining).  
* A build generating 10x the normal log volume (potential data exfiltration).  
* A build executing steps in an undefined order.

Manual log review is impossible at scale. Therefore, an automated, ML-driven solution is required to learn "normal" baseline behavior and flag deviations.2

## **3\. System Scope and Constraints**

### **3.1 In-Scope**

* **Ingestion:** Real-time collection of logs via Webhooks from GitHub Actions/GitLab CI.  
* **Architecture:** Fully containerized microservices communicating via a message broker.  
* **ML Core:** Implementation of **Isolation Forest** for metric-based anomaly detection (Build Duration, Log Volume, Event Frequency).4  
* **Data:** Synthetic generation of training datasets containing both normal and attack scenarios.  
* **UI:** A dashboard for visualizing build health and anomaly alerts.

### **3.2 Out-of-Scope**

* Deep semantic text analysis using LLMs (BERT/GPT) due to hardware constraints.  
* Real-time blocking of pipelines (the system is passive/monitoring only).  
* Production-grade authentication (basic auth is sufficient for academic scope).

### **3.3 Hardware Constraints**

The system must run on a single node with:

* **CPU:** Intel Core i5-10300H  
* **RAM:** 16GB (Shared between Docker containers and OS)  
* **GPU:** NVIDIA GTX 1650 (4GB VRAM) – Utilized for accelerated data processing (cuML) if applicable, or left available for future extensions.1

## **4\. Functional Requirements (FR)**

### **FR1: Log Ingestion Service (LogCollector)**

* **FR1.1:** The service MUST expose a REST API endpoint (e.g., POST /webhook) to receive JSON payloads from CI providers.  
* **FR1.2:** The service MUST validate the payload signature (HMAC) to ensure authenticity.  
* **FR1.3:** The service MUST publish the raw log data to a message queue (RabbitMQ/Redis) for asynchronous processing.

### **FR2: Log Parsing Service (LogParser)**

* **FR2.1:** The service MUST consume raw logs from the message queue.  
* **FR2.2:** The service MUST utilize the **Drain algorithm** to parse unstructured log lines into structured "Log Templates" and "Event IDs".5  
* **FR2.3:** The service MUST extract numerical features from the parsed logs:  
  * *Build Duration* (timestamp delta).  
  * *Log Line Count*.  
  * *Error/Warning Count* (regex matching).  
  * *Template Frequency* (vector of Event ID counts).

### **FR3: Anomaly Detection Service (AnomalyDetector)**

* **FR3.1:** The service MUST implement the **Isolation Forest** algorithm using scikit-learn.4  
* **FR3.2:** The model MUST support **Unsupervised Learning**, training on unlabeled historical data to establish a baseline of "normality".2  
* **FR3.3:** The service MUST expose an API to receive a feature vector and return an Anomaly Score (-1 for anomaly, 1 for normal).4  
* **FR3.4:** The service MUST periodically retrain (or refit) the model as new "normal" data accumulates.

### **FR4: Synthetic Data Generator (DataFactory)**

* **FR4.1:** A standalone Python script MUST be provided to generate synthetic CI/CD logs.  
* **FR4.2:** The generator MUST be capable of injecting specific attack signatures:  
  * *Cryptomining:* artificially inflating build duration.2  
  * *Exfiltration:* inflating log volume or network request counts.3

### **FR5: Visualization Dashboard (Dashboard)**

* **FR5.1:** A web frontend MUST display a list of analyzed builds.  
* **FR5.2:** Anomalous builds MUST be visually distinct (e.g., red highlighting).  
* **FR5.3:** Users MUST be able to click a build to see *why* it was flagged (e.g., "Duration 500s \> Baseline 120s").

## **5\. Architectural Design**

The system follows an **Event-Driven Microservices Architecture**.

### **5.1 Technology Stack**

| Component | Technology | Justification |
| :---- | :---- | :---- |
| **API Gateway / Ingestion** | Node.js (Express) | High concurrency for handling webhooks. |
| **Message Broker** | RabbitMQ or Redis | Decouples ingestion from heavy processing.1 |
| **Parser & ML Engine** | Python 3.9+ | Native support for Scikit-learn and LogPai/Drain. |
| **Primary Database** | MongoDB | Storing unstructured raw logs and parsed templates.1 |
| **Metric Database** | PostgreSQL \+ TimescaleDB | Efficient storage of time-series features (duration, counts) for the Isolation Forest.1 |
| **Frontend** | React.js | Responsive UI for the dashboard.1 |

### **5.2 Data Flow Pipeline**

1. **Ingest:** LogCollector receives a webhook $\\rightarrow$ Pushes payload to queue:raw\_logs.  
2. **Parse:** LogParser subscribes to queue:raw\_logs $\\rightarrow$ Runs Drain Parsing $\\rightarrow$ Extracts Features $\\rightarrow$ Pushes Feature Vector to queue:features.  
3. **Detect:** AnomalyDetector subscribes to queue:features $\\rightarrow$ Runs Inference (Isolation Forest) $\\rightarrow$ Saves Result (Score) to TimescaleDB.  
4. **Visualize:** Dashboard polls TimescaleDB to display real-time status.

## **6\. Machine Learning Strategy: Option A (Isolation Forest)**

### **6.1 Feature Engineering Plan**

The Isolation Forest algorithm excels at detecting anomalies in high-dimensional tabular data. We will convert raw logs into the following feature vectors per build execution:

1. **Total Duration ($T\_d$):** $T\_{end} \- T\_{start}$ (Seconds).  
2. **Log Volume ($V\_l$):** Total number of lines generated.  
3. **Character Density ($D\_c$):** Average characters per line (detects obfuscated binary dumps).  
4. **Event Distribution:** A "Bag-of-Events" vector representing the frequency of specific log templates (e.g., "Docker Build", "Test Failed").

### **6.2 Model Configuration**

* **Algorithm:** sklearn.ensemble.IsolationForest  
* **Contamination Parameter:** Set to auto or 0.01 (assuming 1% attack rate in synthetic data).  
* **n\_estimators:** 100 (Sufficient for stability without overloading the CPU).  
* **Training Data:** The model will be trained on the "Normal" subset of the synthetic data generated by the DataFactory component.

### **6.3 Hardware Optimization**

* **Memory Efficiency:** Isolation Forest is CPU-bound and memory-efficient. It typically requires \<500MB RAM for datasets under 100k samples, fitting easily within the 16GB limit.  
* **GPU Usage:** The GTX 1650 is not strictly required for Scikit-learn's Isolation Forest. However, if performance becomes a bottleneck, we can utilize **NVIDIA RAPIDS (cuML)** to run Isolation Forest entirely on the GPU.8

## **7\. Data Strategy & Synthetic Generation**

Since real-world labeled attack data is scarce, the project relies on synthetic data.

### **7.1 Generator Logic (synthetic\_generator.py)**

The script will use the faker library to generate logs mimicking the following structure:

* **Normal Profile:**  
  * Steps: Checkout \-\> Install Dependencies \-\> Run Tests \-\> Build Artifact \-\> Deploy.  
  * Duration: Gaussian distribution centered at 120s ($\\sigma=15s$).  
* **Attack Profile A (Cryptomining):**  
  * Steps: Normal steps \+ hidden xmrig process.  
  * Duration: Gaussian distribution centered at 600s.  
* **Attack Profile B (Exfiltration):**  
  * Steps: Normal steps \+ curl \-X POST loops.  
  * Log Volume: 5x \- 10x standard deviation above mean.

## **8\. Implementation Roadmap**

### **Phase 1: Foundation (Week 1-2)**

* Set up Docker Compose environment (Mongo, Postgres, RabbitMQ).  
* Implement LogCollector to receive dummy JSON.  
* Develop synthetic\_generator.py to create training\_data.csv.

### **Phase 2: Core Logic (Week 3-5)**

* Implement LogParser with Drain algorithm.  
* Implement AnomalyDetector service.  
  * Train IsolationForest on training\_data.csv.  
  * Serialize model using joblib.  
  * Create inference endpoint.

### **Phase 3: Integration & UI (Week 6-8)**

* Connect services via RabbitMQ.  
* Build React Dashboard to query Postgres/TimescaleDB.  
* End-to-end testing: Inject a "Cryptomining" log via LogCollector and verify the Dashboard shows a red alert.

### **Phase 4: Documentation & Final Polish (Week 9\)**

* Finalize API documentation (Swagger/OpenAPI).  
* Write project report detailing the accuracy (Precision/Recall) of the model on test data.

## **9\. Success Metrics**

* **Accuracy:** The model should achieve \>90% recall on synthetic anomaly datasets.4  
* **Latency:** End-to-end processing (Ingest to Alert) should take \<5 seconds for a standard build log.  
* **Stability:** All microservices should auto-recover (restart) upon failure (Docker Restart Policies).

This PRD provides the definitive roadmap for building SafeOps-LogMiner using the Isolation Forest approach. It balances educational value with technical feasibility, ensuring a successful delivery on your available hardware.

### **References**

* 1 SafeOps Requirements & Hardware Constraints.  
* 2 CI/CD Attack Vectors (Cryptomining, Exfiltration).  
* 5 Drain Log Parsing Algorithm.  
* 4 Isolation Forest for Anomaly Detection.  
* 8 RAPIDS cuML for GPU Acceleration.  
* Microservices Patterns (Message Queues).

#### **Works cited**

1. SafeOps.pdf  
2. What Is Cryptojacking? \- Palo Alto Networks, accessed December 7, 2025, [https://www.paloaltonetworks.com/cyberpedia/cryptojacking](https://www.paloaltonetworks.com/cyberpedia/cryptojacking)  
3. Top 10 Indicators of Compromise in CI/CD Pipelines | Xygeni, accessed December 7, 2025, [https://xygeni.io/blog/top-10-indicators-of-compromise-in-ci-cd-pipelines/](https://xygeni.io/blog/top-10-indicators-of-compromise-in-ci-cd-pipelines/)  
4. Anomaly Detection in Python with Isolation Forest \- DigitalOcean, accessed December 7, 2025, [https://www.digitalocean.com/community/tutorials/anomaly-detection-isolation-forest](https://www.digitalocean.com/community/tutorials/anomaly-detection-isolation-forest)  
5. logparser/logparser/Drain/README.md at main · logpai/logparser \- GitHub, accessed December 7, 2025, [https://github.com/logpai/logparser/blob/master/logparser/Drain/README.md](https://github.com/logpai/logparser/blob/master/logparser/Drain/README.md)  
6. Drain: An Online Log Parsing Approach with Fixed Depth Tree \- Jieming Zhu, accessed December 7, 2025, [https://jiemingzhu.github.io/pub/pjhe\_icws2017.pdf](https://jiemingzhu.github.io/pub/pjhe_icws2017.pdf)  
7. GHALogs: Large-Scale Dataset of GitHub Actions Runs \- Zenodo, accessed December 7, 2025, [https://zenodo.org/records/10154920](https://zenodo.org/records/10154920)  
8. logpai/loglizer: A machine learning toolkit for log-based anomaly detection \[ISSRE'16\], accessed December 7, 2025, [https://github.com/logpai/loglizer](https://github.com/logpai/loglizer)  
9. Out of Memory; BERT \- nlp \- Stack Overflow, accessed December 7, 2025, [https://stackoverflow.com/questions/59638747/out-of-memory-bert](https://stackoverflow.com/questions/59638747/out-of-memory-bert)