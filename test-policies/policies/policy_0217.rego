package compliance.validation.resource.allow.policy_0217

# Auto-generated policy 217 (Rego v1 syntax)
# Package: compliance.validation.resource.allow

# Metadata
metadata := {
    "policy_id": "0217",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0217_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0217_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
