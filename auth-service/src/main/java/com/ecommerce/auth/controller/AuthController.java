package com.ecommerce.auth.controller;

import com.ecommerce.auth.dto.AuthResponse;
import com.ecommerce.auth.dto.LoginRequest;
import com.ecommerce.auth.dto.RegisterRequest;
import com.ecommerce.auth.model.User;
import com.ecommerce.auth.repository.UserRepository;
import com.ecommerce.auth.util.JwtUtil;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.dao.QueryTimeoutException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.springframework.dao.DataIntegrityViolationException;

@RestController
@RequestMapping("/api/v1/auth")
public class AuthController {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtUtil jwtUtil;
    private final RedisTemplate<String, User> redisTemplate;
    private static final Logger logger = LoggerFactory.getLogger(AuthController.class);

    @Value("${jwt.secret:9a4f2c8d3b7a1e5f8c3d6b2a1f4e7d9c8b7a6f5e4d3c2b1a0f9e8d7c6b5a4f3e}")
    private String jwtSecret;

    public AuthController(UserRepository userRepository, PasswordEncoder passwordEncoder, JwtUtil jwtUtil, RedisTemplate<String, User> redisTemplate) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.jwtUtil = jwtUtil;
        this.redisTemplate = redisTemplate;
    }

    @PostMapping("/register")
    public ResponseEntity<String> register(@RequestBody RegisterRequest request) {
        if (userRepository.findByUsername(request.getUsername()).isPresent()) {
            return ResponseEntity.badRequest().body("Username already exists");
        }
        User user = User.builder()
                .username(request.getUsername())
                .password(passwordEncoder.encode(request.getPassword()))
                .email(request.getEmail())
                .role("USER")
                .build();
        userRepository.save(user);
        return ResponseEntity.ok("User registered successfully");
    }

    @PostMapping("/login")
    public ResponseEntity<AuthResponse> login(@RequestBody LoginRequest request) {
        User user = null;
        try {
            user = redisTemplate.opsForValue().get("user:" + request.getUsername());
        } catch (QueryTimeoutException | RedisConnectionFailureException e) {
            logger.warn("[WARN] Redis down, falling back to PostgreSQL...");
        }

        if (user == null) {
            user = userRepository.findByUsername(request.getUsername()).orElse(null);
            if (user != null) {
                try {
                    redisTemplate.opsForValue().set("user:" + user.getUsername(), user, Duration.ofHours(1));
                } catch (Exception e) {
                    logger.warn("Redis caching failed: {}", e.getMessage());
                }
            }
        }

        if (user != null && passwordEncoder.matches(request.getPassword(), user.getPassword())) {
            String token = jwtUtil.generateToken(user.getUsername());
            return ResponseEntity.ok(new AuthResponse(token, user.getUsername()));
        }
        
        return ResponseEntity.status(401).build();
    }

    @PostMapping("/validate")
    public ResponseEntity<String> validate(@RequestBody String token) {
        long delay = FailureInjectionController.getValidationDelayMs();
        if (delay > 0) {
            try {
                Thread.sleep(delay);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
        
        try {
            SecretKey key = Keys.hmacShaKeyFor(jwtSecret.getBytes(StandardCharsets.UTF_8));
            Claims claims = Jwts.parser()
                    .verifyWith(key)
                    .build()
                    .parseSignedClaims(token)
                    .getPayload();
                    
            String username = claims.getSubject();
            User user = null;
            try {
                user = redisTemplate.opsForValue().get("user:" + username);
            } catch (QueryTimeoutException | RedisConnectionFailureException e) {
                logger.warn("[WARN] Redis down, falling back to PostgreSQL...");
            }
            
            if (user == null) {
                user = userRepository.findByUsername(username).orElse(null);
                if (user != null) {
                    try {
                        redisTemplate.opsForValue().set("user:" + username, user, Duration.ofHours(1));
                    } catch (Exception e) {
                        logger.warn("Redis caching failed: {}", e.getMessage());
                    }
                }
            }
            
            if (user != null) {
                return ResponseEntity.ok(username);
            } else {
                return ResponseEntity.status(401).body("User not found");
            }
        } catch (Exception e) {
            return ResponseEntity.status(401).body(e.getMessage());
        }
    }

    @GetMapping("/chaos/corruption")
    public ResponseEntity<String> simulateCorruption() {
        throw new DataIntegrityViolationException("Duplicate entry for key 'PRIMARY'");
    }
}
