package compliance.validation.policy.verify.policy_0993

# Auto-generated policy 993 (Rego v1 syntax)
# Package: compliance.validation.policy.verify

# Metadata
metadata := {
    "policy_id": "0993",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0993_allowed = false
policy_0993_allowed if {
    input.user.active
    input.resource.public
}
policy_0993_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
