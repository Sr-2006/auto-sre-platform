package com.autosre.orderservice.exception;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.dao.DataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger logger = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    private Map<String, Object> buildResponse(HttpServletRequest request, HttpStatus status, String error, String message) {
        Map<String, Object> response = new HashMap<>();
        response.put("timestamp", Instant.now().toString());
        response.put("status", status.value());
        response.put("error", error);
        response.put("message", message);
        response.put("path", request.getRequestURI());
        
        String correlationId = request.getHeader("X-Correlation-ID");
        response.put("correlationId", correlationId != null ? correlationId : "");
        return response;
    }

    @ExceptionHandler(DataAccessException.class)
    public ResponseEntity<Map<String, Object>> handleDatabaseExceptions(DataAccessException ex, HttpServletRequest request) {
        logger.error("[SRE-LOG-EVENT] System Failure: {}. StackTrace: ", request.getRequestURI(), ex);
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(
            buildResponse(request, HttpStatus.SERVICE_UNAVAILABLE, "Service Unavailable", "Database connection error. Please try again later.")
        );
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> handleValidationExceptions(MethodArgumentNotValidException ex, HttpServletRequest request) {
        logger.error("[SRE-LOG-EVENT] System Failure: {}. StackTrace: ", request.getRequestURI(), ex);
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(
            buildResponse(request, HttpStatus.BAD_REQUEST, "Bad Request", "Invalid request parameters.")
        );
    }

    @ExceptionHandler(Throwable.class)
    public ResponseEntity<Map<String, Object>> handleGenericExceptions(Throwable ex, HttpServletRequest request) {
        logger.error("[SRE-LOG-EVENT] System Failure: {}. StackTrace: ", request.getRequestURI(), ex);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(
            buildResponse(request, HttpStatus.INTERNAL_SERVER_ERROR, "Internal Server Error", "An unexpected error occurred.")
        );
    }
}
