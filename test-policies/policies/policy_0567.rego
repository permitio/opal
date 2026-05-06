package security.monitoring.resource.verify.policy_0567

# Auto-generated policy 567 (Rego v1 syntax)
# Package: security.monitoring.resource.verify

# Metadata
metadata := {
    "policy_id": "0567",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0567_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0567_allowed if {
    input.user.role == "admin"
}
policy_0567_allowed if {
    data.policies.security.enabled
}
