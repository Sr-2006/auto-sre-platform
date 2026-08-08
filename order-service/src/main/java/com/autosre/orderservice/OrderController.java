package com.autosre.orderservice;

import jakarta.persistence.QueryTimeoutException;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {

    @PostMapping
    public ResponseEntity<String> placeOrder() {
        return ResponseEntity.ok("Order successfully placed");
    }

    @GetMapping("/chaos/timeout")
    public ResponseEntity<String> simulateTimeout() {
        throw new QueryTimeoutException("Connection timed out after 30s");
    }

    @GetMapping("/chaos/logic_fail")
    public ResponseEntity<String> simulateLogicFail() {
        throw new NullPointerException("User context is null");
    }

    @GetMapping("/chaos/error")
    public ResponseEntity<String> simulateError() {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body("Simulated Database Crash");
    }
}
