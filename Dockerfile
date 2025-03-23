FROM public.ecr.aws/lambda/python:3.13

# Copy requirements first to leverage Docker cache
COPY requirements.txt /tmp/

# Install dependencies
RUN pip3 install --upgrade pip && \
    pip3 install --no-cache-dir -r /tmp/requirements.txt

# Copy function code
COPY src/ ${LAMBDA_TASK_ROOT}/src/

# Set the handler
CMD [ "src.lambda_function.lambda_handler" ]
