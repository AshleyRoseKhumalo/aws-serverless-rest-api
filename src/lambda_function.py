
import json
import os
import boto3
from decimal import Decimal

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(
    os.environ.get("TABLE_NAME", "DevOpsProducts")
)


def json_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json"
        },
        "body": json.dumps(body, default=str)
    }


def lambda_handler(event, context):
    try:
        method = (
            event.get("httpMethod")
            or event.get("requestContext", {})
                    .get("http", {})
                    .get("method")
        )

        if not method:
            return json_response(400, {
                "message": "Missing HTTP method"
            })

        path_parameters = event.get("pathParameters") or {}
        product_id = path_parameters.get("id")

        # GET /products - List all products
        if method == "GET" and not product_id:
            response = table.scan()
            items = response.get("Items", [])

            while "LastEvaluatedKey" in response:
                response = table.scan(
                    ExclusiveStartKey=response["LastEvaluatedKey"]
                )
                items.extend(response.get("Items", []))

            return json_response(200, items)

        # GET /products/{id} - Retrieve one product
        if method == "GET" and product_id:
            response = table.get_item(
                Key={"ProductID": product_id}
            )

            item = response.get("Item")

            if not item:
                return json_response(404, {
                    "message": "Product not found"
                })

            return json_response(200, item)

        # POST /products - Create product
        if method == "POST":
            body = json.loads(event.get("body") or "{}")

            product_id = body.get("ProductID")
            product_name = body.get("ProductName")

            if not product_id or not product_name:
                return json_response(400, {
                    "message": "ProductID and ProductName are required"
                })

            product = {
                "ProductID": str(product_id),
                "ProductName": str(product_name),
                "Price": Decimal(str(body.get("Price", 0))),
                "Quantity": int(body.get("Quantity", 0))
            }

            table.put_item(
                Item=product,
                ConditionExpression="attribute_not_exists(ProductID)"
            )

            return json_response(201, {
                "message": "Product created",
                "product": product
            })

        # PUT /products/{id} - Update product
        if method == "PUT" and product_id:
            body = json.loads(event.get("body") or "{}")

            updates = []
            values = {}
            names = {}

            for field in ["ProductName", "Price", "Quantity"]:
                if field in body:
                    value = body[field]

                    if field == "Price":
                        value = Decimal(str(value))
                    elif field == "Quantity":
                        value = int(value)

                    placeholder = f"#{field}"
                    value_placeholder = f":{field}"

                    updates.append(
                        f"{placeholder} = {value_placeholder}"
                    )
                    names[placeholder] = field
                    values[value_placeholder] = value

            if not updates:
                return json_response(400, {
                    "message": "No fields to update"
                })

            response = table.update_item(
                Key={"ProductID": product_id},
                UpdateExpression="SET " + ", ".join(updates),
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
                ConditionExpression="attribute_exists(ProductID)",
                ReturnValues="ALL_NEW"
            )

            return json_response(200, response["Attributes"])

        # DELETE /products/{id} - Delete product
        if method == "DELETE" and product_id:
            table.delete_item(
                Key={"ProductID": product_id},
                ConditionExpression="attribute_exists(ProductID)"
            )

            return json_response(200, {
                "message": "Product deleted"
            })

        return json_response(405, {
            "message": "Method not allowed"
        })

    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        return json_response(409, {
            "message": "Product already exists or does not exist"
        })

    except (ValueError, TypeError, json.JSONDecodeError):
        return json_response(400, {
            "message": "Invalid request data"
        })

    except Exception:
        print("Unexpected error", flush=True)
        import traceback
        traceback.print_exc()

        return json_response(500, {
            "message": "Internal server error"
        })
