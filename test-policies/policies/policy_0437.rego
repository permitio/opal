package compliance.authorization.user.verify.policy_0437

# Auto-generated policy 437 (Rego v1 syntax)
# Package: compliance.authorization.user.verify

# Metadata
metadata := {
    "policy_id": "0437",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0437_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0437_allowed = false
