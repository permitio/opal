package risk.enforcement.action.deny.policy_0236

# Auto-generated policy 236 (Rego v1 syntax)
# Package: risk.enforcement.action.deny

# Metadata
metadata := {
    "policy_id": "0236",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0236_allowed if {
    input.user.active
    input.resource.public
}
default policy_0236_allowed = false
policy_0236_allowed if {
    input.user.role == "admin"
}
policy_0236_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
