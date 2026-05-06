package risk.authentication.user.allow.policy_0456

# Auto-generated policy 456 (Rego v1 syntax)
# Package: risk.authentication.user.allow

# Metadata
metadata := {
    "policy_id": "0456",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0456_allowed if {
    input.user.role == "admin"
}
policy_0456_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0456_allowed if {
    input.user.active
    input.resource.public
}
default policy_0456_allowed = false
